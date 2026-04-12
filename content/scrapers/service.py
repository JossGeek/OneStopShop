import logging
import os
from datetime import timedelta
from copy import deepcopy

import requests
from django.db import transaction
from django.utils import timezone

from content.models import (
    Domain,
    Offer,
    OfferDomain,
    OfferType,
    Organization,
    ScrapingJob,
    ScrapingRun,
    SourceType,
    TargetProfile,
    User,
)
from content.scrapers.extractors import extract_deterministic
from content.scrapers.ollama_client import OllamaClient
from content.scrapers.source_registry import get_sources
from content.scrapers.types import ExtractedPayload, SourceDefinition
from content.seeding import uuid_from_token

LOGGER = logging.getLogger(__name__)


class ScrapeService:
    def __init__(self, source_keys: list[str] | None = None, dry_run: bool = False, use_llm_fallback: bool = True):
        self.source_keys = source_keys
        self.dry_run = dry_run
        self.use_llm_fallback = use_llm_fallback
        self.request_timeout_seconds = int(os.getenv("SCRAPER_TIMEOUT_SECONDS", "30"))
        self.user_agent = os.getenv(
            "SCRAPER_USER_AGENT",
            "SUNRISE-OSS-Scraper/1.0 (+https://github.com/EnzoBellicaud/OneStopShop)",
        )
        self.llm_threshold = float(os.getenv("SCRAPER_LLM_FALLBACK_THRESHOLD", "0.60"))
        self.ollama_client = OllamaClient()

    def run(self) -> dict:
        sources = get_sources(self.source_keys)
        if not sources:
            return {
                "sources": 0,
                "offers_processed": 0,
                "offers_created": 0,
                "offers_updated": 0,
                "offers_unchanged": 0,
                "offers_flagged_stale": 0,
                "errors": 0,
                "llm_calls": 0,
            }

        source_type = SourceType.objects.get(name="scraping")
        ingestion_user = self._get_ingestion_user()

        stats = {
            "sources": 0,
            "offers_processed": 0,
            "offers_created": 0,
            "offers_updated": 0,
            "offers_unchanged": 0,
            "offers_flagged_stale": 0,
            "errors": 0,
            "llm_calls": 0,
        }
        seen_keys: set[tuple[str, str, str]] = set()
        successful_source_keys: set[str] = set()

        for source in sources:
            stats["sources"] += 1
            job = self._sync_job(source)
            run = ScrapingRun.objects.create(
                job=job,
                source_key=source.key,
                status=ScrapingRun.RunStatus.RUNNING,
                started_at=timezone.now(),
            )

            try:
                result = self._process_source(source, source_type, ingestion_user)
                run.status = ScrapingRun.RunStatus.SUCCESS
                run.offers_processed = 1
                run.offers_created = int(result["action"] == "created")
                run.offers_updated = int(result["action"] == "updated")
                run.offers_unchanged = int(result["action"] == "unchanged")
                run.llm_calls_count = int(result["llm_used"])
                run.log = [result["log"]]

                stats["offers_processed"] += 1
                stats["offers_created"] += run.offers_created
                stats["offers_updated"] += run.offers_updated
                stats["offers_unchanged"] += run.offers_unchanged
                stats["llm_calls"] += run.llm_calls_count
                seen_keys.add(result["natural_key"])
                successful_source_keys.add(source.key)
            except Exception as exc:  # pragma: no cover - runtime network behavior
                run.status = ScrapingRun.RunStatus.FAILED
                run.errors_count = 1
                run.log = [self._build_error_log(source, exc)]
                stats["errors"] += 1
                if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
                    status_code = exc.response.status_code
                    if status_code in {404, 410}:
                        LOGGER.warning(
                            "Scraping source not found for %s (HTTP %s)",
                            source.key,
                            status_code,
                        )
                    else:
                        LOGGER.exception("Scraping failed for %s", source.key)
                else:
                    LOGGER.exception("Scraping failed for %s", source.key)
            finally:
                now = timezone.now()
                run.completed_at = now
                run.save()
                job.last_run_at = now
                job.next_run_at = now + timedelta(minutes=source.interval_minutes)
                job.save(update_fields=["last_run_at", "next_run_at", "updated_at"])

        stale_count = self._flag_stale_candidates(
            sources,
            seen_keys,
            successful_source_keys,
            ingestion_user,
        )
        stats["offers_flagged_stale"] = stale_count

        return stats

    def _get_ingestion_user(self) -> User:
        username = os.getenv("INGESTION_BOT_USERNAME", "ingestion_bot")
        user = User.objects.filter(username=username).first()
        if user:
            return user

        return User.objects.create(
            id=uuid_from_token("user_ingestion_bot"),
            username=username,
            email="ingestion-bot@oss.local",
            password_hash="seeded-not-for-auth",
        )

    def _sync_job(self, source: SourceDefinition) -> ScrapingJob:
        job, _ = ScrapingJob.objects.update_or_create(
            key=source.key,
            defaults={
                "name": source.name,
                "source_domain": self._domain_from_url(source.url),
                "status": ScrapingJob.JobStatus.ACTIVE,
                "is_active": source.enabled,
                "run_interval_minutes": source.interval_minutes,
                "use_llm_fallback": source.llm_fallback_enabled,
            },
        )
        return job

    @staticmethod
    def _domain_from_url(url: str) -> str:
        without_scheme = url.split("//", 1)[-1]
        return without_scheme.split("/", 1)[0]

    def _process_source(self, source: SourceDefinition, source_type: SourceType, ingestion_user: User) -> dict:
        html = self._fetch_html(source)
        extracted = extract_deterministic(html, source)

        llm_used = False
        if self.use_llm_fallback and source.llm_fallback_enabled:
            if extracted.confidence < self.llm_threshold or not extracted.summary or not extracted.title:
                llm_payload = self.ollama_client.extract_fallback(html, source, extracted)
                if llm_payload is not None and llm_payload.confidence >= extracted.confidence:
                    extracted = llm_payload
                    llm_used = True

        action, natural_key = self._upsert_offer(source, source_type, ingestion_user, extracted)

        return {
            "action": action,
            "llm_used": llm_used,
            "natural_key": natural_key,
            "log": {
                "source": source.key,
                "url": source.url,
                "method": extracted.method,
                "confidence": extracted.confidence,
                "action": action,
            },
        }

    def _fetch_html(self, source: SourceDefinition) -> str:
        response = requests.get(
            source.url,
            headers={"User-Agent": self.user_agent, "Accept-Language": "en-US,en;q=0.9"},
            timeout=self.request_timeout_seconds,
        )
        response.raise_for_status()
        return response.text

    def _upsert_offer(
        self,
        source: SourceDefinition,
        source_type: SourceType,
        ingestion_user: User,
        extracted: ExtractedPayload,
    ) -> tuple[str, tuple[str, str, str]]:
        organization = Organization.objects.get(id=uuid_from_token(source.organization_token))
        offer_type = OfferType.objects.get(name=source.offer_type)
        target_profile = TargetProfile.objects.get(name=source.target_profile)

        natural_key = (source.url, str(organization.id), str(offer_type.id))

        existing = Offer.objects.filter(
            link=source.url,
            organization=organization,
            offer_type=offer_type,
        ).first()

        current_timestamp = timezone.now().isoformat()

        scraping_metadata = {
            "managed": True,
            "source_key": source.key,
            "quality": source.quality,
            "method": extracted.method,
            "confidence": extracted.confidence,
            "last_seen_at": current_timestamp,
            "stale_candidate": False,
        }

        merged_details = {
            **(extracted.details or {}),
            "scraping": scraping_metadata,
        }

        if existing is None:
            if self.dry_run:
                return "created", natural_key

            offer = Offer.objects.create(
                title=extracted.title,
                summary=extracted.summary,
                link=source.url,
                country=source.country,
                details=merged_details,
                source_type=source_type,
                target_profile=target_profile,
                organization=organization,
                status=Offer.OfferStatus.DRAFT,
                created_by=ingestion_user,
                updated_by=ingestion_user,
                offer_type=offer_type,
            )
            self._replace_domains(offer, source.domain_names)
            return "created", natural_key

        existing_domain_names = set(existing.domains.values_list("name", flat=True))
        source_domain_names = set(source.domain_names)

        changed = (
            existing.title != extracted.title
            or existing.summary != extracted.summary
            or existing.country != source.country
            or existing.target_profile_id != target_profile.id
            or existing_domain_names != source_domain_names
            or self._normalized_details_for_compare(existing.details)
            != self._normalized_details_for_compare(merged_details)
        )

        if not changed:
            if not self.dry_run:
                # Keep the freshness marker up to date even when content is unchanged.
                existing.details = merged_details
                existing.updated_by = ingestion_user
                existing.save(update_fields=["details", "updated_by", "updated_at"])
            return "unchanged", natural_key

        if self.dry_run:
            return "updated", natural_key

        existing.title = extracted.title
        existing.summary = extracted.summary
        existing.country = source.country
        existing.details = merged_details
        existing.source_type = source_type
        existing.target_profile = target_profile
        existing.updated_by = ingestion_user
        existing.save(
            update_fields=[
                "title",
                "summary",
                "country",
                "details",
                "source_type",
                "target_profile",
                "updated_by",
                "updated_at",
            ]
        )
        self._replace_domains(existing, source.domain_names)
        return "updated", natural_key

    def _replace_domains(self, offer: Offer, domain_names: list[str]) -> None:
        domain_map = {
            domain.name: domain
            for domain in Domain.objects.filter(name__in=domain_names)
        }
        OfferDomain.objects.filter(offer=offer).delete()
        OfferDomain.objects.bulk_create(
            [
                OfferDomain(offer=offer, domain=domain_map[name])
                for name in domain_names
                if name in domain_map
            ]
        )

    def _flag_stale_candidates(
        self,
        sources: list[SourceDefinition],
        seen_keys: set[tuple[str, str, str]],
        successful_source_keys: set[str],
        ingestion_user: User,
    ) -> int:
        source_keys = {source.key for source in sources}
        stale_count = 0
        for offer in Offer.objects.filter(source_type__name="scraping"):
            details = offer.details or {}
            scraping = details.get("scraping")
            if not isinstance(scraping, dict):
                continue
            source_key = scraping.get("source_key")
            if source_key not in source_keys:
                continue
            if source_key not in successful_source_keys:
                continue

            natural_key = (offer.link, str(offer.organization_id), str(offer.offer_type_id))
            if natural_key in seen_keys:
                continue

            if scraping.get("stale_candidate"):
                continue

            stale_count += 1
            if self.dry_run:
                continue

            scraping["stale_candidate"] = True
            scraping["stale_marked_at"] = timezone.now().isoformat()
            scraping["stale_reason"] = "missing_from_latest_source_fetch"
            details["scraping"] = scraping
            offer.details = details
            offer.updated_by = ingestion_user
            offer.save(update_fields=["details", "updated_by", "updated_at"])

        return stale_count

    @staticmethod
    def _normalized_details_for_compare(details: dict | None) -> dict:
        if not isinstance(details, dict):
            return {}

        normalized = deepcopy(details)
        scraping = normalized.get("scraping")
        if isinstance(scraping, dict):
            for key in ("last_seen_at", "stale_candidate", "stale_marked_at", "stale_reason"):
                scraping.pop(key, None)
            normalized["scraping"] = scraping
        return normalized

    @staticmethod
    def _build_error_log(source: SourceDefinition, exc: Exception) -> dict:
        error_entry = {
            "error": str(exc),
            "source": source.key,
            "url": source.url,
            "error_type": exc.__class__.__name__,
        }
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            error_entry["http_status"] = exc.response.status_code
        return error_entry


@transaction.atomic
def run_scrape(source_keys: list[str] | None = None, dry_run: bool = False, use_llm_fallback: bool = True) -> dict:
    service = ScrapeService(
        source_keys=source_keys,
        dry_run=dry_run,
        use_llm_fallback=use_llm_fallback,
    )
    return service.run()
