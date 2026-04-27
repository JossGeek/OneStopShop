from django.core.management.base import BaseCommand
from django.db import transaction

from content.models import (
    ContactRole,
    Domain,
    OfferType,
    Organization,
    SourceType,
    TargetProfile,
    User,
    UserOrganization,
    UserRole,
)
from content.seeding import load_task2_seed, uuid_from_token


class Command(BaseCommand):
    help = "Seeds lookup/reference tables and foundational organizations/users."

    @transaction.atomic
    def handle(self, *args, **options):
        data = load_task2_seed()

        for row in data["offer_types"]:
            OfferType.objects.update_or_create(
                id=uuid_from_token(row["id"].strip("{}")),
                defaults={"name": row["name"], "description": row["description"]},
            )

        for row in data["domains"]:
            Domain.objects.update_or_create(
                id=uuid_from_token(row["id"].strip("{}")),
                defaults={"name": row["name"]},
            )

        for row in data["target_profiles"]:
            TargetProfile.objects.update_or_create(
                id=uuid_from_token(row["id"].strip("{}")),
                defaults={"name": row["name"], "description": row["description"]},
            )

        for row in data["source_types"]:
            SourceType.objects.update_or_create(
                id=uuid_from_token(row["id"].strip("{}")),
                defaults={"name": row["name"], "description": row["description"]},
            )

        for row in data["user_roles"]:
            UserRole.objects.update_or_create(
                id=uuid_from_token(row["id"].strip("{}")),
                defaults={"name": row["name"], "description": row["description"]},
            )

        for row in data["contact_roles"]:
            ContactRole.objects.update_or_create(
                id=uuid_from_token(row["value"]),
                defaults={"value": row["value"], "description": row["description"]},
            )

        organizations = [
            {
                "token": "unibz",
                "name": "Free University of Bozen-Bolzano (UNIBZ)",
                "country": "IT",
                "website": "https://www.unibz.it/en/",
            },
            {
                "token": "mdu",
                "name": "Malardalen University (MDU)",
                "country": "SE",
                "website": "https://www.mdu.se/en/malardalen-university",
            },
            {
                "token": "tu_ilmenau",
                "name": "TU Ilmenau",
                "country": "DE",
                "website": "https://www.tu-ilmenau.de/",
            },
            {
                "token": "uitm",
                "name": "University of Information Technology and Management (UITM)",
                "country": "PL",
                "website": "https://www.uitm.edu.eu/",
            },
            {
                "token": "utc",
                "name": "Université de Technologie de Compiègne (UTC)",
                "country": "FR",
                "website": "https://www.utc.fr/",
            },
            {
                "token": "euc",
                "name": "European University Cyprus (EUC)",
                "country": "CY",
                "website": "https://www.euc.ac.cy/",
            },
            {
                "token": "univpm",
                "name": "Università Politecnica delle Marche (UNIVPM)",
                "country": "IT",
                "website": "https://www.univpm.it/",
            },
            {
                "token": "unmo",
                "name": "University of Mostar (UNMO)",
                "country": "BA",
                "website": "https://www.unmo.ba/",
            },
            {
                "token": "ipvc",
                "name": "Instituto Politécnico de Viana do Castelo (IPVC)",
                "country": "PT",
                "website": "https://www.ipvc.pt/",
            },
        ]

        organization_map = {}
        for row in organizations:
            org, _ = Organization.objects.update_or_create(
                id=uuid_from_token(row["token"]),
                defaults={
                    "name": row["name"],
                    "type": Organization.OrganizationType.UNIVERSITY,
                    "country": row["country"],
                    "website": row["website"],
                },
            )
            organization_map[row["token"]] = org

        users = [
            {
                "token": "user_ingestion_bot",
                "username": "ingestion_bot",
                "email": "ingestion-bot@oss.local",
            },
            {
                "token": "user_admin_unibz",
                "username": "admin_unibz",
                "email": "admin-unibz@oss.local",
                "org_token": "unibz",
            },
            {
                "token": "user_admin_mdu",
                "username": "admin_mdu",
                "email": "admin-mdu@oss.local",
                "org_token": "mdu",
            },
        ]

        admin_role = UserRole.objects.get(name="admin")
        for row in users:
            user, _ = User.objects.update_or_create(
                id=uuid_from_token(row["token"]),
                defaults={
                    "username": row["username"],
                    "email": row["email"],
                    "password_hash": "seeded-not-for-auth",
                },
            )

            if "org_token" in row:
                UserOrganization.objects.update_or_create(
                    user=user,
                    organization=organization_map[row["org_token"]],
                    role=admin_role,
                )

        # Remove deprecated types. Safe: scraper no longer assigns these;
        # Offer FK is PROTECT so deletion will surface any orphaned offers
        # that need manual reclassification rather than silently losing data.
        removed_types = OfferType.objects.filter(
            name__in=["mobility", "expertise", "event"]
        )
        for ot in removed_types:
            orphans = ot.offers.count()
            if orphans:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping removal of offer_type '{ot.name}' — {orphans} offer(s) still reference it. Reclassify first."
                    )
                )
            else:
                ot.delete()
                self.stdout.write(f"  Removed deprecated offer_type: {ot.name}")

        removed_domains = Domain.objects.filter(
            name__in=["Multilingualism", "Industry_collaboration"]
        )
        for dom in removed_domains:
            dom.delete()
            self.stdout.write(f"  Removed deprecated domain: {dom.name}")

        self.stdout.write(self.style.SUCCESS("Lookup and foundational seed completed."))
