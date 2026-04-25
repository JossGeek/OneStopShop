import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class TimeStampedModel(models.Model):
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		abstract = True


class OfferType(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = "offer_type"
		ordering = ["name"]


class Domain(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=150, unique=True)

	class Meta:
		db_table = "domain"
		ordering = ["name"]


class TargetProfile(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = "target_profile"
		ordering = ["name"]


class SourceType(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = "source_type"
		ordering = ["name"]


class UserRole(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = "user_role"
		ordering = ["name"]


class ContactRole(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	value = models.CharField(max_length=120, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = "contact_role"
		ordering = ["value"]


class Organization(TimeStampedModel):
	class OrganizationType(models.TextChoices):
		UNIVERSITY = "university", "University"
		COMPANY = "company", "Company"
		OTHER = "other", "Other"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	name = models.CharField(max_length=255)
	type = models.CharField(max_length=30, choices=OrganizationType.choices)
	country = models.CharField(max_length=2)
	website = models.URLField(max_length=500)

	class Meta:
		db_table = "organization"
		ordering = ["name"]
		constraints = [
			models.CheckConstraint(
				condition=Q(country__regex=r"^[A-Z]{2}$"),
				name="organization_country_iso2",
			),
		]


class User(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	username = models.CharField(max_length=150, unique=True)
	email = models.EmailField(unique=True)
	password_hash = models.CharField(max_length=255)

	class Meta:
		db_table = "oss_user"
		ordering = ["username"]


class UserOrganization(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organization_links")
	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name="user_links",
	)
	role = models.ForeignKey(UserRole, on_delete=models.PROTECT, related_name="user_links")

	class Meta:
		db_table = "user_organization"
		constraints = [
			models.UniqueConstraint(
				fields=["user", "organization", "role"],
				name="uniq_user_org_role",
			),
		]


class Contact(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	contact_name = models.CharField(max_length=255)
	email = models.EmailField(blank=True, null=True)
	phone = models.CharField(max_length=50, blank=True, null=True)
	role = models.ForeignKey(ContactRole, on_delete=models.PROTECT, related_name="contacts")
	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name="contacts",
		blank=True,
		null=True,
	)
	contact_approved = models.BooleanField(default=False)

	class Meta:
		db_table = "contact"
		ordering = ["contact_name"]


class Offer(TimeStampedModel):
	class OfferStatus(models.TextChoices):
		DRAFT = "draft", "Draft"
		PUBLISHED = "published", "Published"
		ARCHIVED = "archived", "Archived"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	title = models.CharField(max_length=255)
	summary = models.TextField()
	link = models.URLField(max_length=1000)
	country = models.CharField(max_length=2)
	details = models.JSONField(default=dict)
	source_type = models.ForeignKey(SourceType, on_delete=models.PROTECT, related_name="offers")
	target_profile = models.ForeignKey(
		TargetProfile,
		on_delete=models.PROTECT,
		related_name="offers",
	)
	organization = models.ForeignKey(
		Organization,
		on_delete=models.CASCADE,
		related_name="offers",
	)
	status = models.CharField(
		max_length=20,
		choices=OfferStatus.choices,
		default=OfferStatus.DRAFT,
	)
	created_by = models.ForeignKey(
		User,
		on_delete=models.PROTECT,
		related_name="created_offers",
	)
	updated_by = models.ForeignKey(
		User,
		on_delete=models.PROTECT,
		related_name="updated_offers",
	)
	offer_type = models.ForeignKey(OfferType, on_delete=models.PROTECT, related_name="offers")
	domains = models.ManyToManyField(Domain, through="OfferDomain", related_name="offers")
	contacts = models.ManyToManyField(Contact, through="OfferContact", related_name="offers")

	class Meta:
		db_table = "offer"
		ordering = ["title"]
		constraints = [
			models.CheckConstraint(
				condition=Q(country__regex=r"^[A-Z]{2}$"),
				name="offer_country_iso2",
			),
		]


class OfferDomain(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
	domain = models.ForeignKey(Domain, on_delete=models.CASCADE)

	class Meta:
		db_table = "offer_domain"
		constraints = [
			models.UniqueConstraint(
				fields=["offer", "domain"],
				name="uniq_offer_domain",
			),
		]


class OfferContact(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
	contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
	role_label = models.CharField(max_length=50, default="primary_contact")

	class Meta:
		db_table = "offer_contact"
		constraints = [
			models.UniqueConstraint(
				fields=["offer", "contact"],
				name="uniq_offer_contact",
			),
		]


class ScrapingJob(TimeStampedModel):
	class JobStatus(models.TextChoices):
		ACTIVE = "active", "Active"
		PAUSED = "paused", "Paused"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	key = models.CharField(max_length=120, unique=True)
	name = models.CharField(max_length=255)
	source_domain = models.CharField(max_length=255)
	status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.ACTIVE)
	is_active = models.BooleanField(default=True)
	run_interval_minutes = models.PositiveIntegerField(default=360)
	use_llm_fallback = models.BooleanField(default=True)
	last_run_at = models.DateTimeField(blank=True, null=True)
	next_run_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		db_table = "scraping_job"
		ordering = ["key"]


class ScrapingRun(TimeStampedModel):
	class RunStatus(models.TextChoices):
		PENDING = "pending", "Pending"
		RUNNING = "running", "Running"
		SUCCESS = "success", "Success"
		PARTIAL = "partial", "Partial"
		FAILED = "failed", "Failed"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	job = models.ForeignKey(
		ScrapingJob,
		on_delete=models.PROTECT,
		related_name="runs",
		blank=True,
		null=True,
	)
	source_key = models.CharField(max_length=120, blank=True)
	status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING)
	started_at = models.DateTimeField(blank=True, null=True)
	completed_at = models.DateTimeField(blank=True, null=True)
	offers_processed = models.PositiveIntegerField(default=0)
	offers_created = models.PositiveIntegerField(default=0)
	offers_updated = models.PositiveIntegerField(default=0)
	offers_unchanged = models.PositiveIntegerField(default=0)
	offers_flagged_stale = models.PositiveIntegerField(default=0)
	offers_deleted = models.PositiveIntegerField(default=0)
	llm_calls_count = models.PositiveIntegerField(default=0)
	errors_count = models.PositiveIntegerField(default=0)
	log = models.JSONField(default=list)

	class Meta:
		db_table = "scraping_run"
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["status"], name="idx_scraping_run_status"),
			models.Index(fields=["source_key", "-created_at"], name="idx_scraping_run_source"),
		]


class UserProfile(TimeStampedModel):
	# Profile preferences stay lightweight for Stage 1 so the API can expose
	# dashboard-ready data without introducing more relational tables than needed.
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
	bio = models.TextField(blank=True, default="")
	avatar_url = models.URLField(max_length=500, blank=True, null=True)
	preferred_domains = models.JSONField(default=list, blank=True)
	preferred_countries = models.JSONField(default=list, blank=True)
	notification_enabled = models.BooleanField(default=True)

	class Meta:
		db_table = "user_profile"


class UserNeed(TimeStampedModel):
	class NeedStatus(models.TextChoices):
		ACTIVE = "active", "Active"
		FULFILLED = "fulfilled", "Fulfilled"
		ARCHIVED = "archived", "Archived"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="needs")
	title = models.CharField(max_length=255)
	description = models.TextField()
	target_profile = models.ForeignKey(
		TargetProfile,
		on_delete=models.PROTECT,
		related_name="user_needs",
	)
	status = models.CharField(
		max_length=20,
		choices=NeedStatus.choices,
		default=NeedStatus.ACTIVE,
	)
	countries = models.JSONField(default=list, blank=True)
	domains = models.ManyToManyField(Domain, through="UserNeedDomain", related_name="user_needs")

	class Meta:
		db_table = "user_need"
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["user", "status"], name="idx_user_need_status"),
			models.Index(fields=["user", "-created_at"], name="idx_user_need_created"),
		]


class UserNeedDomain(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user_need = models.ForeignKey(UserNeed, on_delete=models.CASCADE, related_name="domain_links")
	domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="user_need_links")

	class Meta:
		db_table = "user_need_domain"
		constraints = [
			models.UniqueConstraint(
				fields=["user_need", "domain"],
				name="uniq_user_need_domain",
			),
		]


class UserFavorite(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorites")
	offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="favorited_by")
	note = models.TextField(blank=True, default="")

	class Meta:
		db_table = "user_favorite"
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "offer"],
				name="uniq_user_favorite",
			),
		]
		indexes = [
			models.Index(fields=["user", "-created_at"], name="idx_user_favorite_created"),
		]


class MatchingHit(TimeStampedModel):
	class MatchStatus(models.TextChoices):
		NEW = "new", "New"
		VIEWED = "viewed", "Viewed"
		INTERESTED = "interested", "Interested"
		DECLINED = "declined", "Declined"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="matching_hits")
	need = models.ForeignKey(UserNeed, on_delete=models.CASCADE, related_name="matching_hits")
	offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="matching_hits")
	match_score = models.DecimalField(
		max_digits=5,
		decimal_places=4,
		validators=[MinValueValidator(0), MaxValueValidator(1)],
	)
	match_reason = models.TextField()
	status = models.CharField(
		max_length=20,
		choices=MatchStatus.choices,
		default=MatchStatus.NEW,
	)
	viewed_at = models.DateTimeField(blank=True, null=True)

	class Meta:
		db_table = "matching_hit"
		ordering = ["-match_score", "-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["need", "offer"],
				name="uniq_matching_hit_need_offer",
			),
			models.CheckConstraint(
				condition=Q(match_score__gte=0) & Q(match_score__lte=1),
				name="matching_hit_score_range",
			),
		]
		indexes = [
			models.Index(fields=["user", "status"], name="idx_matching_hit_status"),
			models.Index(fields=["user", "-match_score"], name="idx_matching_hit_score"),
		]
