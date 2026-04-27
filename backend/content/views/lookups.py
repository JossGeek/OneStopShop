from django.http import JsonResponse
from django.views.decorators.http import require_GET

from content.models import Domain, Offer, OfferType, Organization, TargetProfile


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
def organizations(request):
    data = list(
        Organization.objects.order_by("name").values("id", "name", "type", "country")
    )
    for row in data:
        row["id"] = str(row["id"])
    return JsonResponse({"count": len(data), "results": data})


@require_GET
def target_profiles(request):
    data = list(
        TargetProfile.objects.order_by("name").values("id", "name", "description")
    )
    for row in data:
        row["id"] = str(row["id"])
    return JsonResponse({"count": len(data), "results": data})


@require_GET
def countries(request):
    rows = list(
        Offer.objects.order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )
    data = [{"code": code} for code in rows if code]
    return JsonResponse({"count": len(data), "results": data})
