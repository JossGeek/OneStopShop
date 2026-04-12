import uuid

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
