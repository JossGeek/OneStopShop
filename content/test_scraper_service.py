import uuid
from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from content.models import (
    Domain,
    Offer,
    OfferDomain,
    OfferType,
    Organization,
    ScrapingRun,
    SourceType,
    TargetProfile,
    User,
)
from content.scrapers.service import run_scrape
from content.scrapers.types import ExtractedPayload, SourceDefinition
from content.seeding import uuid_from_token


class ScrapeServiceBehaviorTests(TestCase):
    def setUp(self):
        self.source_type_scraping = SourceType.objects.create(name="scraping", description="")
        self.offer_type = OfferType.objects.create(name="training", description="")
        self.target_profile = TargetProfile.objects.create(name="student", description="")
        self.domain = Domain.objects.create(name="AI")
        self.organization = Organization.objects.create(
            id=uuid_from_token("unibz"),
            name="UNIBZ",
            type=Organization.OrganizationType.UNIVERSITY,
            country="IT",
            website="https://www.unibz.it",
        )
        self.user = User.objects.create(
            id=uuid.uuid4(),
            username="seed-user",
            email="seed-user@example.com",
            password_hash="not-used",
        )
        self.source = SourceDefinition(
            key="test_source",
            name="Test Source",
            url="https://example.edu/test-source",
            organization_token="unibz",
            offer_type="training",
            target_profile="student",
            country="IT",
            domain_names=["AI"],
        )

    def _create_offer(self, details: dict) -> Offer:
        offer = Offer.objects.create(
            id=uuid.uuid4(),
            title="Stable Title",
            summary="Stable Summary",
            link=self.source.url,
            country="IT",
            details=details,
            status=Offer.OfferStatus.DRAFT,
            source_type=self.source_type_scraping,
            target_profile=self.target_profile,
            organization=self.organization,
            offer_type=self.offer_type,
            created_by=self.user,
            updated_by=self.user,
        )
        OfferDomain.objects.create(offer=offer, domain=self.domain)
        return offer

    @patch("content.scrapers.service.get_sources")
    @patch("content.scrapers.service.requests.get")
    def test_http_404_marks_run_failed_without_stale_flagging(self, mock_get, mock_get_sources):
        self._create_offer(
            {
                "source_name": "Test Source",
                "scraping": {
                    "source_key": "test_source",
                    "stale_candidate": False,
                },
            }
        )

        mock_get_sources.return_value = [self.source]
        response = requests.Response()
        response.status_code = 404
        response.url = self.source.url
        mock_get.side_effect = requests.exceptions.HTTPError(
            "404 Client Error: Not Found",
            response=response,
        )

        summary = run_scrape(use_llm_fallback=False)

        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["offers_flagged_stale"], 0)

        run = ScrapingRun.objects.get(source_key="test_source")
        self.assertEqual(run.status, ScrapingRun.RunStatus.FAILED)
        self.assertEqual(run.errors_count, 1)
        self.assertEqual(run.log[0]["error_type"], "HTTPError")
        self.assertEqual(run.log[0]["http_status"], 404)

        offer = Offer.objects.get(link=self.source.url)
        self.assertFalse(offer.details["scraping"]["stale_candidate"])

    @patch("content.scrapers.service.get_sources")
    @patch("content.scrapers.service.extract_deterministic")
    @patch("content.scrapers.service.requests.get")
    def test_unchanged_offer_is_counted_as_unchanged_and_freshened(
        self,
        mock_get,
        mock_extract,
        mock_get_sources,
    ):
        self._create_offer(
            {
                "source_name": "Test Source",
                "extra": "stable",
                "scraping": {
                    "managed": True,
                    "source_key": "test_source",
                    "quality": "real",
                    "method": "deterministic",
                    "confidence": 0.9,
                    "last_seen_at": "2020-01-01T00:00:00+00:00",
                    "stale_candidate": True,
                    "stale_reason": "old-flag",
                },
            }
        )

        mock_get_sources.return_value = [self.source]
        mock_response = Mock()
        mock_response.text = "<html><h1>ignored</h1></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        mock_extract.return_value = ExtractedPayload(
            title="Stable Title",
            summary="Stable Summary",
            details={"source_name": "Test Source", "extra": "stable"},
            confidence=0.9,
            method="deterministic",
        )

        summary = run_scrape(use_llm_fallback=False)

        self.assertEqual(summary["offers_processed"], 1)
        self.assertEqual(summary["offers_unchanged"], 1)
        self.assertEqual(summary["offers_updated"], 0)
        self.assertEqual(summary["errors"], 0)

        offer = Offer.objects.get(link=self.source.url)
        scraping = offer.details["scraping"]
        self.assertFalse(scraping["stale_candidate"])
        self.assertNotEqual(scraping["last_seen_at"], "2020-01-01T00:00:00+00:00")
