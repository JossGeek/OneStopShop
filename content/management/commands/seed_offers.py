from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from content.models import Domain, Offer, OfferDomain, OfferType, Organization, SourceType, TargetProfile, User
from content.seeding import FICTIONAL_OFFER_PLACEHOLDERS, load_task3_samples, resolve_uuid


class Command(BaseCommand):
    help = "Seeds Task 3 sample offers (real + illustrative only)."

    @transaction.atomic
    def handle(self, *args, **options):
        payload = load_task3_samples()
        offers = payload["offers"]

        inserted = 0
        skipped = 0
        for row in offers:
            if row["id"] in FICTIONAL_OFFER_PLACEHOLDERS:
                skipped += 1
                continue

            offer_type = OfferType.objects.get(id=resolve_uuid(row["offer_type_id"]))
            organization = Organization.objects.get(id=resolve_uuid(row["organization_id"]))
            source_type = SourceType.objects.get(id=resolve_uuid(row["source_type_id"]))
            target_profile = TargetProfile.objects.get(id=resolve_uuid(row["target_profile_id"]))
            created_by = User.objects.get(id=resolve_uuid(row["created_by"]))
            updated_by = User.objects.get(id=resolve_uuid(row["updated_by"]))

            offer_id = resolve_uuid(row["id"])
            defaults = {
                "id": offer_id,
                "title": row["title"],
                "summary": row["summary"],
                "link": row["link"],
                "country": row["country"],
                "status": row["status"],
                "details": row["details"],
                "offer_type": offer_type,
                "organization": organization,
                "source_type": source_type,
                "target_profile": target_profile,
                "created_by": created_by,
                "updated_by": updated_by,
            }

            offer, created = Offer.objects.get_or_create(
                link=row["link"],
                organization=organization,
                offer_type=offer_type,
                defaults=defaults,
            )

            if not created:
                for field_name, value in defaults.items():
                    if field_name == "id":
                        continue
                    setattr(offer, field_name, value)
                offer.save()

            Offer.objects.filter(id=offer.id).update(
                created_at=parse_datetime(row["created_at"]),
                updated_at=parse_datetime(row["updated_at"]),
            )

            OfferDomain.objects.filter(offer=offer).delete()
            for domain_id in row["domain_ids"]:
                domain = Domain.objects.get(id=resolve_uuid(domain_id))
                OfferDomain.objects.create(offer=offer, domain=domain)

            inserted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Offer seed completed. Inserted/updated: {inserted}. Skipped fictional records: {skipped}."
            )
        )
