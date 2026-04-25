import logging
import os
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import requests
from django.db import transaction
from django.utils import timezone

from content.models import (
    CrawlUrl,
    Offer,
    OfferType,
    Organization,
    ScrapingRun,
    SourceType,
)
from content.scrapers.extractors import extract_deterministic, is_generic_page
from content.scrapers.service import ScrapeService, _ts
from content.scrapers.source_registry import get_sources
from content.scrapers.types import SourceDefinition
from content.seeding import uuid_from_token

LOGGER = logging.getLogger(__name__)

_BACKOFF_HOURS = [1, 6, 24]


class CrawlerService(ScrapeService):
    """Discovers URLs from source seeds and writes them to the CrawlUrl queue."""

    def run(self) -> dict:
        sources = get_sources(self.source_keys)
        stats = {"sources": 0, "discovered": 0, "new": 0, "already_known": 0, "errors": 0}

        for source in sources:
            stats["sources"] += 1
            LOGGER.info("[%s] Crawler starting — %s", source.key, source.url)
            try:
                result = self._crawl_source(source)
                stats["discovered"] += result["discovered"]
                stats["new"] += result["new"]
                stats["already_known"] += result["already_known"]
                LOGGER.info(
                    "[%s] Crawler done — discovered=%d new=%d known=%d",
                    source.key, result["discovered"], result["new"], result["already_known"],
                )
            except Exception:
                stats["errors"] += 1
                LOGGER.exception("[%s] Crawler failed", source.key)

        return stats

    def _crawl_source(self, source: SourceDefinition) -> dict:
        if source.crawl_enabled:
            urls, _ = self._discover_urls_bfs(source)
        else:
            urls = [source.url]

        new_count = 0
        known_count = 0

        for url in urls:
            crawl_url, created = CrawlUrl.objects.get_or_create(
                source_key=source.key,
                url=url,
                defaults={
                    "status": CrawlUrl.UrlStatus.PENDING,
                    "next_check_at": timezone.now(),
                },
            )
            if created:
                new_count += 1
            elif crawl_url.status != CrawlUrl.UrlStatus.ARCHIVED:
                known_count += 1

        return {"discovered": len(urls), "new": new_count, "already_known": known_count}


class UrlScraperService(ScrapeService):
    """Picks pending/due URLs from CrawlUrl queue, scrapes them, updates offers."""

    def __init__(self, use_llm_fallback: bool = True):
        super().__init__(use_llm_fallback=use_llm_fallback)
        self.batch_size = int(os.getenv("SCRAPER_BATCH_SIZE", "10"))
        self.revisit_days = int(os.getenv("SCRAPER_REVISIT_DAYS", "7"))
        self.max_consecutive_errors = int(os.getenv("SCRAPER_MAX_CONSECUTIVE_ERRORS", "3"))

    def run_batch(self) -> dict:
        batch = self._claim_batch()
        if not batch:
            LOGGER.debug("URL scraper — no URLs due")
            return {"processed": 0, "created": 0, "updated": 0, "unchanged": 0, "archived": 0, "errors": 0, "neglected": 0}

        source_type = SourceType.objects.get(name="scraping")
        ingestion_user = self._get_ingestion_user()
        source_map = {s.key: s for s in get_sources()}

        stats = {"processed": 0, "created": 0, "updated": 0, "unchanged": 0, "archived": 0, "errors": 0, "neglected": 0}
        logs: list[dict] = []

        LOGGER.info("URL scraper batch — size=%d", len(batch))

        run = ScrapingRun.objects.create(
            source_key="url_scraper_batch",
            status=ScrapingRun.RunStatus.RUNNING,
            started_at=timezone.now(),
        )

        for crawl_url in batch:
            if crawl_url.source_key.startswith("import__"):
                self._scrape_import_url(crawl_url, ingestion_user, stats, logs)
                continue

            source = source_map.get(crawl_url.source_key)
            if source is None:
                LOGGER.warning("URL scraper — source_key %r not in registry, archiving", crawl_url.source_key)
                crawl_url.status = CrawlUrl.UrlStatus.ARCHIVED
                crawl_url.last_error = "source_key removed from registry"
                crawl_url.save()
                stats["archived"] += 1
                continue

            self._scrape_one(crawl_url, source, source_type, ingestion_user, stats, logs)

        run.status = ScrapingRun.RunStatus.SUCCESS
        run.offers_processed = stats["processed"]
        run.offers_created = stats["created"]
        run.offers_updated = stats["updated"]
        run.offers_unchanged = stats["unchanged"]
        run.errors_count = stats["errors"]
        run.urls_neglected = stats["neglected"]
        run.log = logs
        run.completed_at = timezone.now()
        run.save()

        LOGGER.info(
            "URL scraper batch done — processed=%d created=%d updated=%d archived=%d errors=%d neglected=%d",
            stats["processed"], stats["created"], stats["updated"],
            stats["archived"], stats["errors"], stats["neglected"],
        )
        return stats

    def _claim_batch(self) -> list[CrawlUrl]:
        with transaction.atomic():
            batch = list(
                CrawlUrl.objects.select_for_update(skip_locked=True)
                .filter(
                    status__in=[
                        CrawlUrl.UrlStatus.PENDING,
                        CrawlUrl.UrlStatus.DONE,
                        CrawlUrl.UrlStatus.ERROR,
                    ],
                    next_check_at__lte=timezone.now(),
                )
                .order_by("next_check_at")[: self.batch_size]
            )
            for crawl_url in batch:
                crawl_url.status = CrawlUrl.UrlStatus.PROCESSING
                crawl_url.save(update_fields=["status", "updated_at"])
        return batch

    def _scrape_one(
        self,
        crawl_url: CrawlUrl,
        source: SourceDefinition,
        source_type: SourceType,
        ingestion_user,
        stats: dict,
        logs: list[dict],
    ) -> None:
        page_source = replace(source, url=crawl_url.url)

        try:
            html, canonical_url = self._fetch_html_url(crawl_url.url)
        except requests.exceptions.HTTPError as exc:
            http_status = exc.response.status_code if exc.response is not None else None
            self._handle_http_error(crawl_url, http_status, stats)
            logs.append({"ts": _ts(), "event": "url_failed", "level": "warn",
                         "source_key": source.key, "url": crawl_url.url,
                         "http_status": http_status, "reason": "http_error"})
            return
        except requests.RequestException as exc:
            self._handle_transient_error(crawl_url, str(exc), None, stats)
            logs.append({"ts": _ts(), "event": "url_failed", "level": "warn",
                         "source_key": source.key, "url": crawl_url.url, "reason": "request_error",
                         "message": str(exc)})
            return

        use_crawl = source.crawl_enabled
        extracted = extract_deterministic(html, page_source)

        if use_crawl and is_generic_page(extracted.title):
            stats["neglected"] += 1
            LOGGER.info("[%s] NEGLECT %s — generic_page_title", source.key, crawl_url.url)
            logs.append({"ts": _ts(), "event": "url_neglected", "level": "info",
                         "source_key": source.key, "url": crawl_url.url, "reason": "generic_page_title"})
            self._mark_done(crawl_url)
            return

        if use_crawl:
            if self.use_llm_fallback and source.llm_fallback_enabled:
                is_relevant, llm_payload, reason = self.ollama_client.assess_and_extract(
                    html, page_source, extracted
                )
                if llm_payload is not None:
                    stats["processed"] += 0  # just count LLM call
                if not is_relevant:
                    stats["neglected"] += 1
                    LOGGER.info("[%s] NEGLECT %s — %s", source.key, crawl_url.url, reason or "non_relevant_page")
                    logs.append({"ts": _ts(), "event": "url_neglected", "level": "info",
                                 "source_key": source.key, "url": crawl_url.url,
                                 "reason": reason or "non_relevant_page"})
                    self._mark_done(crawl_url)
                    return
                if llm_payload is not None and llm_payload.confidence >= extracted.confidence:
                    extracted = llm_payload
            else:
                if (extracted.title == source.name and extracted.summary.startswith("Auto-extracted from")):
                    stats["neglected"] += 1
                    self._mark_done(crawl_url)
                    return
        else:
            # Non-crawl: LLM is primary. Deterministic is fallback when LLM unavailable/fails.
            if self.use_llm_fallback and source.llm_fallback_enabled:
                llm_payload = self.ollama_client.extract_fallback(html, page_source, extracted)
                if llm_payload is not None:
                    extracted = llm_payload

        if not extracted.title and not extracted.summary:
            stats["neglected"] += 1
            self._mark_done(crawl_url)
            return

        action, _ = self._upsert_offer(page_source, source_type, ingestion_user, extracted)
        LOGGER.info("[%s] MAP %s — %s (conf=%.2f method=%s)", source.key, action.upper(), crawl_url.url, extracted.confidence, extracted.method)

        offer = Offer.objects.filter(
            link=crawl_url.url,
            organization=Organization.objects.get(id=uuid_from_token(source.organization_token)),
            offer_type=OfferType.objects.get(name=source.offer_type),
        ).first()

        crawl_url.offer = offer
        crawl_url.consecutive_errors = 0
        crawl_url.last_error = ""
        self._mark_done(crawl_url)

        stats["processed"] += 1
        if action == "created":
            stats["created"] += 1
        elif action == "updated":
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

        logs.append({"ts": _ts(), "event": "url_processed", "level": "info",
                     "source_key": source.key, "url": crawl_url.url,
                     "method": extracted.method, "confidence": extracted.confidence, "action": action})

    def _scrape_import_url(
        self,
        crawl_url: CrawlUrl,
        ingestion_user,
        stats: dict,
        logs: list[dict],
    ) -> None:
        """Handles CrawlUrl entries created by the bulk import flow (source_key starts with 'import__').
        Uses the linked offer's existing org/type metadata instead of a SourceDefinition lookup.
        Only enriches title/summary/details from the scraped page — does not overwrite org or type.
        """
        offer = crawl_url.offer
        if offer is None:
            LOGGER.warning("Import URL %s has no linked offer — archiving", crawl_url.url)
            crawl_url.status = CrawlUrl.UrlStatus.ARCHIVED
            crawl_url.last_error = "no_linked_offer"
            crawl_url.save()
            stats["archived"] += 1
            return

        # Ensure related fields are loaded
        offer.refresh_from_db()

        try:
            html, _ = self._fetch_html_url(crawl_url.url)
        except requests.exceptions.HTTPError as exc:
            http_status = exc.response.status_code if exc.response is not None else None
            self._handle_http_error(crawl_url, http_status, stats)
            logs.append({"ts": _ts(), "event": "url_failed", "level": "warn",
                         "source_key": crawl_url.source_key, "url": crawl_url.url,
                         "http_status": http_status, "reason": "http_error"})
            return
        except requests.RequestException as exc:
            self._handle_transient_error(crawl_url, str(exc), None, stats)
            logs.append({"ts": _ts(), "event": "url_failed", "level": "warn",
                         "source_key": crawl_url.source_key, "url": crawl_url.url,
                         "reason": "request_error", "message": str(exc)})
            return

        page_source = SimpleNamespace(
            url=crawl_url.url,
            name=offer.title or offer.offer_type.name,
            organization=offer.organization.name,
            offer_type=offer.offer_type.name,
            country=offer.country,
        )
        extracted = extract_deterministic(html, page_source)

        changed = False
        if extracted.title and extracted.title != offer.title:
            offer.title = extracted.title
            changed = True
        if extracted.summary and extracted.summary != offer.summary:
            offer.summary = extracted.summary
            changed = True

        offer.details = {
            **offer.details,
            "scraping": {
                "method": extracted.method,
                "confidence": extracted.confidence,
                "last_seen_at": _ts(),
                "managed": True,
            },
        }
        offer.updated_by = ingestion_user
        offer.save()

        crawl_url.offer = offer
        crawl_url.consecutive_errors = 0
        crawl_url.last_error = ""
        self._mark_done(crawl_url)

        action = "updated" if changed else "unchanged"
        stats["processed"] += 1
        stats[action] += 1
        LOGGER.info("[%s] IMPORT %s — %s (conf=%.2f)", crawl_url.source_key, action.upper(), crawl_url.url, extracted.confidence)
        logs.append({
            "ts": _ts(), "event": "url_processed", "level": "info",
            "source_key": crawl_url.source_key, "url": crawl_url.url,
            "method": extracted.method, "confidence": extracted.confidence, "action": action,
        })

    def _mark_done(self, crawl_url: CrawlUrl) -> None:
        crawl_url.status = CrawlUrl.UrlStatus.DONE
        crawl_url.last_scraped_at = timezone.now()
        crawl_url.next_check_at = timezone.now() + timedelta(days=self.revisit_days)
        crawl_url.save()

    def _handle_http_error(self, crawl_url: CrawlUrl, http_status: int | None, stats: dict) -> None:
        if http_status in {404, 410}:
            LOGGER.info("URL permanently gone (HTTP %s) — %s", http_status, crawl_url.url)
            self._archive_offer(crawl_url)
            crawl_url.status = CrawlUrl.UrlStatus.ARCHIVED
            crawl_url.last_http_status = http_status
            crawl_url.save()
            stats["archived"] += 1
        else:
            self._handle_transient_error(crawl_url, f"HTTP {http_status}", http_status, stats)

    def _handle_transient_error(self, crawl_url: CrawlUrl, error_msg: str, http_status: int | None, stats: dict) -> None:
        crawl_url.consecutive_errors += 1
        crawl_url.last_error = error_msg
        crawl_url.last_http_status = http_status

        if crawl_url.consecutive_errors >= self.max_consecutive_errors:
            LOGGER.warning(
                "URL failed %d times, archiving — %s", crawl_url.consecutive_errors, crawl_url.url
            )
            self._archive_offer(crawl_url)
            crawl_url.status = CrawlUrl.UrlStatus.ARCHIVED
            crawl_url.save()
            stats["archived"] += 1
        else:
            hours = _BACKOFF_HOURS[min(crawl_url.consecutive_errors - 1, len(_BACKOFF_HOURS) - 1)]
            crawl_url.status = CrawlUrl.UrlStatus.ERROR
            crawl_url.next_check_at = timezone.now() + timedelta(hours=hours)
            crawl_url.save()
            stats["errors"] += 1

    def _archive_offer(self, crawl_url: CrawlUrl) -> None:
        if crawl_url.offer_id is None:
            return
        try:
            offer = crawl_url.offer
            if offer.status == Offer.OfferStatus.PUBLISHED:
                offer.status = Offer.OfferStatus.ARCHIVED
                offer.save(update_fields=["status", "updated_at"])
                LOGGER.info("Archived offer — %s", crawl_url.url)
            elif offer.status == Offer.OfferStatus.DRAFT:
                offer.delete()
                LOGGER.info("Deleted draft offer — %s", crawl_url.url)
        except Offer.DoesNotExist:
            pass


def run_crawler(source_keys: list[str] | None = None) -> dict:
    return CrawlerService(source_keys=source_keys).run()


def run_url_scraper_batch(use_llm_fallback: bool = True) -> dict:
    return UrlScraperService(use_llm_fallback=use_llm_fallback).run_batch()
