from uuid import UUID

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from content.models import Domain, Offer, OfferType


def _parse_positive_int(value: str | None, default: int, max_value: int) -> int:
	if value is None:
		return default
	try:
		parsed = int(value)
	except ValueError:
		return default
	if parsed < 1:
		return default
	return min(parsed, max_value)


def _offer_to_dict(offer: Offer) -> dict:
	return {
		"id": str(offer.id),
		"title": offer.title,
		"summary": offer.summary,
		"link": offer.link,
		"country": offer.country,
		"status": offer.status,
		"offer_type": offer.offer_type.name,
		"organization": {
			"id": str(offer.organization.id),
			"name": offer.organization.name,
			"type": offer.organization.type,
			"country": offer.organization.country,
		},
		"source_type": offer.source_type.name,
		"target_profile": offer.target_profile.name,
		"domains": [domain.name for domain in offer.domains.all()],
		"details": offer.details,
		"created_at": offer.created_at.isoformat(),
		"updated_at": offer.updated_at.isoformat(),
	}


@require_GET
def health(request):
	return JsonResponse({"status": "ok"})


@require_GET
def offer_types(request):
	data = list(
		OfferType.objects.order_by("name").values("id", "name", "description")
	)
	for row in data:
		row["id"] = str(row["id"])
	return JsonResponse({"count": len(data), "results": data})


@require_GET
def domains(request):
	data = list(Domain.objects.order_by("name").values("id", "name"))
	for row in data:
		row["id"] = str(row["id"])
	return JsonResponse({"count": len(data), "results": data})


@require_GET
def offers(request):
	queryset = (
		Offer.objects.select_related(
			"offer_type",
			"organization",
			"source_type",
			"target_profile",
		)
		.prefetch_related("domains")
		.order_by("title")
	)

	status = request.GET.get("status")
	if status:
		queryset = queryset.filter(status=status)

	offer_type = request.GET.get("offer_type")
	if offer_type:
		queryset = queryset.filter(offer_type__name=offer_type)

	organization = request.GET.get("organization")
	if organization:
		queryset = queryset.filter(organization__name__icontains=organization)

	target_profile = request.GET.get("target_profile")
	if target_profile:
		queryset = queryset.filter(target_profile__name=target_profile)

	limit = _parse_positive_int(request.GET.get("limit"), default=50, max_value=200)
	rows = list(queryset[:limit])
	payload = [_offer_to_dict(row) for row in rows]

	return JsonResponse(
		{
			"count": len(payload),
			"limit": limit,
			"results": payload,
		}
	)


@require_GET
def offer_detail(request, offer_id: str):
	try:
		parsed_id = UUID(offer_id)
	except ValueError:
		return JsonResponse({"detail": "Invalid offer id."}, status=400)

	offer = (
		Offer.objects.select_related(
			"offer_type",
			"organization",
			"source_type",
			"target_profile",
		)
		.prefetch_related("domains")
		.filter(id=parsed_id)
		.first()
	)
	if offer is None:
		return JsonResponse({"detail": "Offer not found."}, status=404)

	return JsonResponse(_offer_to_dict(offer))
