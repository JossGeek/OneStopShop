import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from content.models import (
	Domain,
	MatchingHit,
	Offer,
	OfferDomain,
	OfferType,
	Organization,
	ScrapingRun,
	SourceType,
	TargetProfile,
	User,
	UserFavorite,
	UserNeed,
	UserNeedDomain,
	UserProfile,
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


class UserDashboardModelTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.domain_ai = Domain.objects.create(name="AI")
		cls.domain_data = Domain.objects.create(name="Data Science")
		cls.target_profile = TargetProfile.objects.create(
			name="research_lab",
			description="Research lab",
		)
		cls.source_type = SourceType.objects.create(name="portal", description="Portal")
		cls.offer_type = OfferType.objects.create(name="grant", description="Grant")
		cls.organization = Organization.objects.create(
			name="Innovation Hub",
			type=Organization.OrganizationType.COMPANY,
			country="DE",
			website="https://innovation.example",
		)
		cls.user = User.objects.create(
			username="dashboard-user",
			email="dashboard@example.com",
			password_hash="secret",
		)
		cls.other_user = User.objects.create(
			username="other-dashboard-user",
			email="other-dashboard@example.com",
			password_hash="secret",
		)
		cls.offer = Offer.objects.create(
			title="AI Collaboration Fund",
			summary="Funding support",
			link="https://innovation.example/offers/ai-fund",
			country="DE",
			details={"kind": "fund"},
			status=Offer.OfferStatus.PUBLISHED,
			source_type=cls.source_type,
			target_profile=cls.target_profile,
			organization=cls.organization,
			created_by=cls.user,
			updated_by=cls.user,
			offer_type=cls.offer_type,
		)

	def test_user_profile_defaults(self):
		profile = UserProfile.objects.create(user=self.user)

		self.assertEqual(profile.bio, "")
		self.assertEqual(profile.preferred_domains, [])
		self.assertEqual(profile.preferred_countries, [])
		self.assertTrue(profile.notification_enabled)

	def test_user_profile_enforces_one_to_one_relationship(self):
		UserProfile.objects.create(user=self.user)

		with self.assertRaises(IntegrityError):
			UserProfile.objects.create(user=self.user)

	def test_user_profile_deleted_with_user(self):
		user = User.objects.create(
			username="profile-owner",
			email="profile-owner@example.com",
			password_hash="secret",
		)
		profile = UserProfile.objects.create(user=user)

		user.delete()

		self.assertFalse(UserProfile.objects.filter(id=profile.id).exists())

	def test_user_need_defaults_to_active_status(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need partners",
			description="Looking for AI partners",
			target_profile=self.target_profile,
		)

		self.assertEqual(need.status, UserNeed.NeedStatus.ACTIVE)
		self.assertEqual(need.countries, [])

	def test_user_need_can_link_domains_via_through_model(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need domain support",
			description="Need AI and data support",
			target_profile=self.target_profile,
		)
		UserNeedDomain.objects.create(user_need=need, domain=self.domain_ai)
		UserNeedDomain.objects.create(user_need=need, domain=self.domain_data)

		self.assertEqual(need.domains.count(), 2)

	def test_user_need_domain_requires_unique_pair(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need unique domain",
			description="Testing unique constraint",
			target_profile=self.target_profile,
		)
		UserNeedDomain.objects.create(user_need=need, domain=self.domain_ai)

		with self.assertRaises(IntegrityError):
			UserNeedDomain.objects.create(user_need=need, domain=self.domain_ai)

	def test_user_need_deleted_with_owner(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need ownership cleanup",
			description="Should be deleted with user",
			target_profile=self.target_profile,
		)

		self.user.delete()

		self.assertFalse(UserNeed.objects.filter(id=need.id).exists())

	def test_user_favorite_allows_blank_note(self):
		favorite = UserFavorite.objects.create(user=self.user, offer=self.offer)

		self.assertEqual(favorite.note, "")

	def test_user_favorite_requires_unique_user_offer_pair(self):
		UserFavorite.objects.create(user=self.user, offer=self.offer)

		with self.assertRaises(IntegrityError):
			UserFavorite.objects.create(user=self.user, offer=self.offer)

	def test_user_favorite_allows_different_users_for_same_offer(self):
		UserFavorite.objects.create(user=self.user, offer=self.offer)
		second = UserFavorite.objects.create(user=self.other_user, offer=self.offer)

		self.assertEqual(second.offer_id, self.offer.id)

	def test_matching_hit_defaults_to_new_status(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need matching",
			description="Matching test",
			target_profile=self.target_profile,
		)
		hit = MatchingHit.objects.create(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="0.9200",
			match_reason="Strong alignment",
		)

		self.assertEqual(hit.status, MatchingHit.MatchStatus.NEW)
		self.assertIsNone(hit.viewed_at)

	def test_matching_hit_requires_unique_need_offer_pair(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need unique match",
			description="Unique match",
			target_profile=self.target_profile,
		)
		MatchingHit.objects.create(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="0.7500",
			match_reason="Good fit",
		)

		with self.assertRaises(IntegrityError):
			MatchingHit.objects.create(
				user=self.user,
				need=need,
				offer=self.offer,
				match_score="0.8000",
				match_reason="Duplicate fit",
			)

	def test_matching_hit_allows_same_offer_for_different_need(self):
		first_need = UserNeed.objects.create(
			user=self.user,
			title="First need",
			description="First",
			target_profile=self.target_profile,
		)
		second_need = UserNeed.objects.create(
			user=self.user,
			title="Second need",
			description="Second",
			target_profile=self.target_profile,
		)
		MatchingHit.objects.create(
			user=self.user,
			need=first_need,
			offer=self.offer,
			match_score="0.6500",
			match_reason="First fit",
		)
		second_hit = MatchingHit.objects.create(
			user=self.user,
			need=second_need,
			offer=self.offer,
			match_score="0.8800",
			match_reason="Second fit",
		)

		self.assertEqual(second_hit.need_id, second_need.id)

	def test_matching_hit_deleted_with_need(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need cascade",
			description="Cascade test",
			target_profile=self.target_profile,
		)
		hit = MatchingHit.objects.create(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="0.9100",
			match_reason="Cascade fit",
		)

		need.delete()

		self.assertFalse(MatchingHit.objects.filter(id=hit.id).exists())

	def test_matching_hit_score_validators_reject_value_below_zero(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need validator low",
			description="Low validator",
			target_profile=self.target_profile,
		)
		hit = MatchingHit(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="-0.1000",
			match_reason="Invalid score",
		)

		with self.assertRaises(ValidationError):
			hit.full_clean()

	def test_matching_hit_score_validators_reject_value_above_one(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need validator high",
			description="High validator",
			target_profile=self.target_profile,
		)
		hit = MatchingHit(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="1.1000",
			match_reason="Invalid score",
		)

		with self.assertRaises(ValidationError):
			hit.full_clean()

	def test_matching_hit_score_accepts_value_between_zero_and_one(self):
		need = UserNeed.objects.create(
			user=self.user,
			title="Need validator valid",
			description="Valid validator",
			target_profile=self.target_profile,
		)
		hit = MatchingHit(
			user=self.user,
			need=need,
			offer=self.offer,
			match_score="0.5000",
			match_reason="Valid score",
		)

		hit.full_clean()

		self.assertEqual(str(hit.match_score), "0.5000")
