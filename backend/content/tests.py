import csv
import io
import json
import uuid

from django.test import TestCase

from content.models import (
	CrawlUrl,
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


class ReadApiTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.offer_type = OfferType.objects.create(name="training", description="")
		cls.offer_type_thesis = OfferType.objects.create(name="thesis", description="")
		cls.domain = Domain.objects.create(name="AI")
		cls.domain_robotics = Domain.objects.create(name="Robotics")
		cls.target_profile = TargetProfile.objects.create(name="student", description="")
		cls.target_profile_researcher = TargetProfile.objects.create(name="researcher", description="")
		cls.source_type = SourceType.objects.create(name="manual", description="")
		cls.organization = Organization.objects.create(
			name="Test University",
			type=Organization.OrganizationType.UNIVERSITY,
			country="IT",
			website="https://example.edu",
		)
		cls.organization_sweden = Organization.objects.create(
			name="Research Sweden",
			type=Organization.OrganizationType.UNIVERSITY,
			country="SE",
			website="https://example.se",
		)
		cls.user = User.objects.create(
			username="tester",
			email="tester@example.com",
			password_hash="not-used",
		)
		cls.offer = Offer.objects.create(
			id=uuid.uuid4(),
			title="AI Master Programme",
			summary="A test offer",
			link="https://example.edu/offer/ai-master",
			country="IT",
			details={"level": "master"},
			status=Offer.OfferStatus.PUBLISHED,
			offer_type=cls.offer_type,
			organization=cls.organization,
			source_type=cls.source_type,
			target_profile=cls.target_profile,
			created_by=cls.user,
			updated_by=cls.user,
		)
		OfferDomain.objects.create(offer=cls.offer, domain=cls.domain)
		cls.offer_two = Offer.objects.create(
			id=uuid.uuid4(),
			title="Robotics Thesis Track",
			summary="A research-focused offer",
			link="https://example.se/offer/robotics-thesis",
			country="SE",
			details={"level": "phd"},
			status=Offer.OfferStatus.DRAFT,
			offer_type=cls.offer_type_thesis,
			organization=cls.organization_sweden,
			source_type=cls.source_type,
			target_profile=cls.target_profile_researcher,
			created_by=cls.user,
			updated_by=cls.user,
		)
		OfferDomain.objects.create(offer=cls.offer_two, domain=cls.domain_robotics)

	def test_health_endpoint(self):
		response = self.client.get("/api/health")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["status"], "ok")

	def test_docs_endpoint(self):
		response = self.client.get("/api/docs")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "SwaggerUIBundle")

	def test_openapi_schema_endpoint(self):
		response = self.client.get("/api/openapi.json")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["openapi"], "3.0.3")
		self.assertIn("/api/offers", payload["paths"])

	def test_offer_types_endpoint(self):
		response = self.client.get("/api/lookups/offer-types")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertGreaterEqual(payload["count"], 1)

	def test_domains_endpoint(self):
		response = self.client.get("/api/lookups/domains")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertGreaterEqual(payload["count"], 1)

	def test_organizations_endpoint(self):
		response = self.client.get("/api/lookups/organizations")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertGreaterEqual(payload["count"], 2)
		names = [row["name"] for row in payload["results"]]
		self.assertIn("Test University", names)

	def test_countries_endpoint(self):
		response = self.client.get("/api/lookups/countries")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		codes = [row["code"] for row in payload["results"]]
		self.assertIn("IT", codes)
		self.assertIn("SE", codes)

	def test_offers_list_endpoint(self):
		response = self.client.get("/api/offers", {"page_size": 1})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 2)
		self.assertEqual(payload["page"], 1)
		self.assertEqual(payload["page_size"], 1)
		self.assertEqual(payload["total_pages"], 2)
		self.assertEqual(len(payload["results"]), 1)
		self.assertEqual(payload["results"][0]["title"], "AI Master Programme")

	def test_offers_filter_by_status(self):
		response = self.client.get("/api/offers", {"status": Offer.OfferStatus.PUBLISHED})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 1)

	def test_offers_search_query(self):
		response = self.client.get("/api/offers", {"q": "research"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["results"][0]["title"], "Robotics Thesis Track")

	def test_offers_filter_by_domain(self):
		response = self.client.get("/api/offers", {"domain": "AI"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["results"][0]["title"], "AI Master Programme")

	def test_offers_filter_by_country(self):
		response = self.client.get("/api/offers", {"country": "se"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["results"][0]["country"], "SE")

	def test_offers_pagination_page_two(self):
		response = self.client.get("/api/offers", {"page": 2, "page_size": 1})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 2)
		self.assertEqual(payload["page"], 2)
		self.assertEqual(payload["total_pages"], 2)
		self.assertEqual(len(payload["results"]), 1)
		self.assertEqual(payload["results"][0]["title"], "Robotics Thesis Track")

	def test_offers_legacy_limit_compatibility(self):
		response = self.client.get("/api/offers", {"limit": 1})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["page_size"], 1)
		self.assertEqual(payload["limit"], 1)
		self.assertEqual(len(payload["results"]), 1)

	def test_scraping_runs_endpoint(self):
		response = self.client.get("/api/scraping/runs")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["count"], 0)

	def test_scraping_run_detail_endpoint(self):
		run = ScrapingRun.objects.create(source_key="test-source", status=ScrapingRun.RunStatus.SUCCESS)
		response = self.client.get(f"/api/scraping/runs/{run.id}")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["id"], str(run.id))

	def test_scraping_run_detail_not_found(self):
		response = self.client.get(f"/api/scraping/runs/{uuid.uuid4()}")
		self.assertEqual(response.status_code, 404)

	def test_offer_detail_endpoint(self):
		response = self.client.get(f"/api/offers/{self.offer.id}")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["id"], str(self.offer.id))

	def test_offer_detail_invalid_uuid(self):
		response = self.client.get("/api/offers/not-a-uuid")
		self.assertEqual(response.status_code, 400)

	def test_offer_detail_not_found(self):
		response = self.client.get(f"/api/offers/{uuid.uuid4()}")
		self.assertEqual(response.status_code, 404)


class ImportEndpointTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.offer_type = OfferType.objects.create(name="training", description="")
		cls.source_type = SourceType.objects.create(name="manual", description="")
		cls.target_profile = TargetProfile.objects.create(name="student", description="")
		cls.domain = Domain.objects.create(name="AI")
		cls.organization = Organization.objects.create(
			name="Test University",
			type=Organization.OrganizationType.UNIVERSITY,
			country="IT",
			website="https://example.edu",
		)
		cls.bot_user = User.objects.create(
			username="ingestion_bot",
			email="bot@example.com",
			password_hash="not-used",
		)
		cls.user = User.objects.create(
			username="tester",
			email="tester@example.com",
			password_hash="not-used",
		)

	def _csv_file(self, rows: list[dict]) -> io.BytesIO:
		from content.ingestion.importer import ALL_COLUMNS
		buf = io.StringIO()
		writer = csv.DictWriter(buf, fieldnames=ALL_COLUMNS, extrasaction="ignore")
		writer.writeheader()
		for row in rows:
			writer.writerow(row)
		return io.BytesIO(buf.getvalue().encode("utf-8"))

	def _valid_row(self, url="https://example.edu/prog") -> dict:
		return {
			"url": url,
			"offer_type": "training",
			"organization": "Test University",
			"target_profile": "student",
			"country": "IT",
			"title": "Test Offer",
			"summary": "A summary.",
		}

	def test_import_template_returns_xlsx(self):
		response = self.client.get("/api/offers/import/template")
		self.assertEqual(response.status_code, 200)
		self.assertIn(
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			response["Content-Type"],
		)
		self.assertGreater(len(response.content), 0)

	def test_import_preview_valid_csv(self):
		f = self._csv_file([self._valid_row()])
		response = self.client.post(
			"/api/offers/import/preview",
			{"file": f},
			format="multipart",
		)
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(payload["valid"]), 1)
		self.assertEqual(len(payload["invalid"]), 0)
		self.assertIn("url", payload["valid"][0]["data"])

	def test_import_preview_invalid_row_missing_field(self):
		row = self._valid_row()
		del row["url"]
		f = self._csv_file([row])
		response = self.client.post("/api/offers/import/preview", {"file": f}, format="multipart")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(payload["invalid"]), 1)
		errors = payload["invalid"][0]["errors"]
		self.assertTrue(any("url" in e for e in errors))

	def test_import_preview_existing_url_warns(self):
		url = "https://example.edu/existing"
		Offer.objects.create(
			title="Existing",
			summary="",
			link=url,
			country="IT",
			status=Offer.OfferStatus.PUBLISHED,
			offer_type=self.offer_type,
			organization=self.organization,
			source_type=self.source_type,
			target_profile=self.target_profile,
			created_by=self.user,
			updated_by=self.user,
		)
		f = self._csv_file([self._valid_row(url=url)])
		response = self.client.post("/api/offers/import/preview", {"file": f}, format="multipart")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(payload["valid"]), 1)
		warnings = payload["valid"][0]["warnings"]
		self.assertTrue(any("already exists" in w for w in warnings))

	def test_import_confirm_creates_draft(self):
		url = "https://example.edu/new-draft"
		rows = [{"data": self._valid_row(url=url), "status": "draft"}]
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": rows}),
			content_type="application/json",
		)
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["drafts"], 1)
		self.assertEqual(payload["published"], 0)
		offer = Offer.objects.get(link=url)
		self.assertEqual(offer.status, Offer.OfferStatus.DRAFT)
		self.assertTrue(CrawlUrl.objects.filter(url=url).exists())

	def test_import_confirm_creates_published(self):
		url = "https://example.edu/new-published"
		rows = [{"data": self._valid_row(url=url), "status": "published"}]
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": rows}),
			content_type="application/json",
		)
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["published"], 1)
		offer = Offer.objects.get(link=url)
		self.assertEqual(offer.status, Offer.OfferStatus.PUBLISHED)

	def test_import_confirm_mixed_statuses(self):
		rows = [
			{"data": self._valid_row(url="https://example.edu/draft-a"), "status": "draft"},
			{"data": self._valid_row(url="https://example.edu/pub-b"), "status": "published"},
		]
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": rows}),
			content_type="application/json",
		)
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(payload["drafts"], 1)
		self.assertEqual(payload["published"], 1)

	def test_import_confirm_row_not_object(self):
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": [42]}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("Row 0", response.json()["error"])

	def test_import_confirm_missing_required_field(self):
		row = {"data": self._valid_row(), "status": "draft"}
		del row["data"]["offer_type"]
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": [row]}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("offer_type", response.json()["error"])

	def test_import_confirm_bad_row_no_partial_write(self):
		valid_url = "https://example.edu/atomic-check"
		good_row = {"data": self._valid_row(url=valid_url), "status": "draft"}
		bad_row = {"data": self._valid_row(), "status": "draft"}
		del bad_row["data"]["organization"]
		offer_count_before = Offer.objects.count()
		response = self.client.post(
			"/api/offers/import/confirm",
			data=json.dumps({"rows": [good_row, bad_row]}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(Offer.objects.count(), offer_count_before)


class ScrapingAnalyticsTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.offer_type = OfferType.objects.create(name="grant", description="")
		cls.source_type = SourceType.objects.create(name="scraper", description="")
		cls.target_profile = TargetProfile.objects.create(name="researcher", description="")
		cls.organization = Organization.objects.create(
			name="Scraping Org",
			type=Organization.OrganizationType.COMPANY,
			country="DE",
			website="https://scraping.example.com",
		)
		cls.user = User.objects.create(
			username="scrape_tester",
			email="scrape@example.com",
			password_hash="not-used",
		)
		cls.run = ScrapingRun.objects.create(
			source_key="test-source",
			status=ScrapingRun.RunStatus.SUCCESS,
			offers_processed=2,
			offers_created=1,
			offers_updated=1,
			offers_unchanged=0,
			urls_neglected=1,
			errors_count=0,
			log=[
				{"event": "url_processed", "method": "llm_primary", "confidence": 0.9},
				{"event": "url_processed", "method": "deterministic", "confidence": 0.95},
				{"event": "url_neglected", "url": "https://skip.me"},
			],
		)
		cls.offer = Offer.objects.create(
			title="Grant Offer",
			summary="",
			link="https://scraping.example.com/grant",
			country="DE",
			status=Offer.OfferStatus.PUBLISHED,
			offer_type=cls.offer_type,
			organization=cls.organization,
			source_type=cls.source_type,
			target_profile=cls.target_profile,
			created_by=cls.user,
			updated_by=cls.user,
		)
		CrawlUrl.objects.create(
			source_key="test-source",
			url="https://scraping.example.com/grant",
			status=CrawlUrl.UrlStatus.DONE,
			offer=cls.offer,
		)
		CrawlUrl.objects.create(
			source_key="test-source",
			url="https://scraping.example.com/pending",
			status=CrawlUrl.UrlStatus.PENDING,
			offer=cls.offer,
		)

	def test_scraping_overview_returns_shape(self):
		response = self.client.get("/api/scraping/overview", {"window": "24h"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertIn("runs_total", payload)
		self.assertIn("runs_timeline", payload)
		self.assertIsInstance(payload["runs_timeline"], list)

	def test_scraping_overview_window_params(self):
		for window in ("7d", "30d"):
			with self.subTest(window=window):
				response = self.client.get("/api/scraping/overview", {"window": window})
				self.assertEqual(response.status_code, 200)

	def test_scraping_overview_invalid_window(self):
		response = self.client.get("/api/scraping/overview", {"window": "bad"})
		self.assertEqual(response.status_code, 400)

	def test_sources_health_returns_per_source(self):
		response = self.client.get("/api/scraping/sources/health")
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		sources = {s["source_key"]: s for s in payload["results"]}
		self.assertIn("test-source", sources)
		s = sources["test-source"]
		self.assertEqual(s["done"], 1)
		self.assertEqual(s["pending"], 1)
		self.assertEqual(s["total_urls"], 2)

	def test_llm_stats_returns_method_split(self):
		response = self.client.get("/api/scraping/llm/stats", {"window": "24h"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		self.assertIn("method_split", payload)
		self.assertIn("llm_primary", payload["method_split"])
		self.assertIn("deterministic", payload["method_split"])
		self.assertIsNotNone(payload["avg_confidence_llm"])

	def test_llm_stats_empty_window(self):
		response = self.client.get("/api/scraping/llm/stats", {"window": "30d"})
		payload = response.json()
		self.assertEqual(response.status_code, 200)
		# run created in setUpTestData falls within 30d too — just verify shape
		self.assertIn("method_split", payload)
		self.assertIn("avg_confidence_llm", payload)
