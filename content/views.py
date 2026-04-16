from math import ceil
from uuid import UUID

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from content.models import Domain, Offer, OfferType, Organization, ScrapingRun


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


def _openapi_spec() -> dict:
	return {
		"openapi": "3.0.3",
		"info": {
			"title": "SUNRISE OSS API",
			"version": "1.0.0",
			"description": "Read-only API for offers, lookup tables, and scraping run telemetry.",
		},
		"servers": [{"url": "/"}],
		"paths": {
			"/api/health": {
				"get": {
					"summary": "Health check",
					"responses": {
						"200": {
							"description": "OK",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/HealthResponse"}
								}
							},
						}
					},
				}
			},
			"/api/lookups/offer-types": {
				"get": {
					"summary": "List offer types",
					"responses": {
						"200": {
							"description": "Offer type lookup entries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/OfferTypeLookupResponse"}
								}
							},
						}
					},
				}
			},
			"/api/lookups/domains": {
				"get": {
					"summary": "List domains",
					"responses": {
						"200": {
							"description": "Domain lookup entries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/DomainLookupResponse"}
								}
							},
						}
					},
				}
			},
			"/api/lookups/organizations": {
				"get": {
					"summary": "List organizations",
					"responses": {
						"200": {
							"description": "Organization lookup entries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/OrganizationLookupResponse"}
								}
							},
						}
					},
				}
			},
			"/api/lookups/countries": {
				"get": {
					"summary": "List countries used by offers",
					"responses": {
						"200": {
							"description": "Country lookup entries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/CountryLookupResponse"}
								}
							},
						}
					},
				}
			},
			"/api/offers": {
				"get": {
					"summary": "List offers",
					"parameters": [
						{"name": "q", "in": "query", "schema": {"type": "string"}},
						{"name": "domain", "in": "query", "schema": {"type": "string"}},
						{"name": "country", "in": "query", "schema": {"type": "string"}},
						{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
						{"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 200}},
						{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 200}},
						{"name": "status", "in": "query", "schema": {"type": "string", "enum": ["draft", "published", "archived"]}},
						{"name": "offer_type", "in": "query", "schema": {"type": "string"}},
						{"name": "organization", "in": "query", "schema": {"type": "string"}},
						{"name": "target_profile", "in": "query", "schema": {"type": "string"}},
					],
					"responses": {
						"200": {
							"description": "Offer list",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/OfferListResponse"}
								}
							},
						}
					},
				}
			},
			"/api/offers/{offer_id}": {
				"get": {
					"summary": "Get offer by id",
					"parameters": [
						{"name": "offer_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
					],
					"responses": {
						"200": {
							"description": "Offer detail",
							"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Offer"}}},
						},
						"400": {
							"description": "Invalid offer id",
							"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
						},
						"404": {
							"description": "Offer not found",
							"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
						},
					},
				}
			},
			"/api/scraping/runs": {
				"get": {
					"summary": "List scraping runs",
					"parameters": [
						{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}}
					],
					"responses": {
						"200": {
							"description": "Scraping run summaries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/ScrapingRunListResponse"}
								}
							},
						}
					},
				}
			},
			"/api/scraping/runs/{run_id}": {
				"get": {
					"summary": "Get scraping run by id",
					"parameters": [
						{"name": "run_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
					],
					"responses": {
						"200": {
							"description": "Scraping run detail",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/ScrapingRunDetail"}
								}
							},
						},
						"400": {
							"description": "Invalid run id",
							"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
						},
						"404": {
							"description": "Scraping run not found",
							"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
						},
					},
				}
			},
		},
		"components": {
			"schemas": {
				"HealthResponse": {
					"type": "object",
					"properties": {"status": {"type": "string", "example": "ok"}},
					"required": ["status"],
				},
				"ErrorResponse": {
					"type": "object",
					"properties": {"detail": {"type": "string"}},
					"required": ["detail"],
				},
				"OfferTypeLookup": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"name": {"type": "string"},
						"description": {"type": "string"},
					},
					"required": ["id", "name", "description"],
				},
				"OfferTypeLookupResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/OfferTypeLookup"}},
					},
					"required": ["count", "results"],
				},
				"DomainLookup": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"name": {"type": "string"},
					},
					"required": ["id", "name"],
				},
				"DomainLookupResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/DomainLookup"}},
					},
					"required": ["count", "results"],
				},
				"OrganizationLookup": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"name": {"type": "string"},
						"type": {"type": "string"},
						"country": {"type": "string"},
					},
					"required": ["id", "name", "type", "country"],
				},
				"OrganizationLookupResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/OrganizationLookup"}},
					},
					"required": ["count", "results"],
				},
				"CountryLookup": {
					"type": "object",
					"properties": {
						"code": {"type": "string"},
					},
					"required": ["code"],
				},
				"CountryLookupResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/CountryLookup"}},
					},
					"required": ["count", "results"],
				},
				"OrganizationSummary": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"name": {"type": "string"},
						"type": {"type": "string"},
						"country": {"type": "string"},
					},
					"required": ["id", "name", "type", "country"],
				},
				"Offer": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"title": {"type": "string"},
						"summary": {"type": "string"},
						"link": {"type": "string", "format": "uri"},
						"country": {"type": "string"},
						"status": {"type": "string", "enum": ["draft", "published", "archived"]},
						"offer_type": {"type": "string"},
						"organization": {"$ref": "#/components/schemas/OrganizationSummary"},
						"source_type": {"type": "string"},
						"target_profile": {"type": "string"},
						"domains": {"type": "array", "items": {"type": "string"}},
						"details": {"type": "object", "additionalProperties": True},
						"created_at": {"type": "string", "format": "date-time"},
						"updated_at": {"type": "string", "format": "date-time"},
					},
					"required": [
						"id", "title", "summary", "link", "country", "status", "offer_type", "organization",
						"source_type", "target_profile", "domains", "details", "created_at", "updated_at"
					],
				},
				"OfferListResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"page": {"type": "integer"},
						"page_size": {"type": "integer"},
						"total_pages": {"type": "integer"},
						"limit": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/Offer"}},
					},
					"required": ["count", "page", "page_size", "total_pages", "limit", "results"],
				},
				"ScrapingRunSummary": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"source_key": {"type": "string"},
						"status": {"type": "string"},
						"job": {"type": "string", "nullable": True},
						"offers_processed": {"type": "integer"},
						"offers_created": {"type": "integer"},
						"offers_updated": {"type": "integer"},
						"offers_unchanged": {"type": "integer"},
						"offers_flagged_stale": {"type": "integer"},
						"errors_count": {"type": "integer"},
						"llm_calls_count": {"type": "integer"},
						"started_at": {"type": "string", "format": "date-time", "nullable": True},
						"completed_at": {"type": "string", "format": "date-time", "nullable": True},
						"created_at": {"type": "string", "format": "date-time"},
					},
					"required": [
						"id", "source_key", "status", "job", "offers_processed", "offers_created", "offers_updated",
						"offers_unchanged", "offers_flagged_stale", "errors_count", "llm_calls_count",
						"started_at", "completed_at", "created_at"
					],
				},
				"ScrapingRunListResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/ScrapingRunSummary"}},
					},
					"required": ["count", "results"],
				},
				"ScrapingRunDetail": {
					"allOf": [
						{"$ref": "#/components/schemas/ScrapingRunSummary"},
						{
							"type": "object",
							"properties": {
								"offers_deleted": {"type": "integer"},
								"log": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
								"updated_at": {"type": "string", "format": "date-time"},
							},
							"required": ["offers_deleted", "log", "updated_at"],
						},
					],
				},
			},
		},
	}


@require_GET
def health(request):
	return JsonResponse({"status": "ok"})


@require_GET
def api_docs(request):
	return render(
		request,
		"content/api_docs.html",
		{"schema_url": reverse("openapi-schema")},
	)


@require_GET
def openapi_schema(request):
	return JsonResponse(_openapi_spec())


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
def countries(request):
	rows = list(
		Offer.objects.order_by("country")
		.values_list("country", flat=True)
		.distinct()
	)
	data = [{"code": code} for code in rows if code]
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

	domain = request.GET.get("domain")
	if domain:
		queryset = queryset.filter(domains__name=domain)

	country = request.GET.get("country")
	if country:
		queryset = queryset.filter(country__iexact=country.strip())

	search_term = request.GET.get("q")
	if search_term:
		queryset = queryset.filter(
			Q(title__icontains=search_term)
			| Q(summary__icontains=search_term)
			| Q(organization__name__icontains=search_term)
		)

	queryset = queryset.distinct()

	legacy_limit = request.GET.get("limit")
	page_size_param = request.GET.get("page_size")
	if page_size_param is None and legacy_limit is not None:
		page_size = _parse_positive_int(legacy_limit, default=50, max_value=200)
	else:
		page_size = _parse_positive_int(page_size_param, default=50, max_value=200)

	page = _parse_positive_int(request.GET.get("page"), default=1, max_value=1000000)
	total_count = queryset.count()
	total_pages = ceil(total_count / page_size) if total_count else 0
	offset = (page - 1) * page_size

	rows = list(queryset[offset:offset + page_size])
	payload = [_offer_to_dict(row) for row in rows]

	return JsonResponse(
		{
			"count": total_count,
			"page": page,
			"page_size": page_size,
			"total_pages": total_pages,
			"limit": page_size,
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


@require_GET
def scraping_runs(request):
	limit = _parse_positive_int(request.GET.get("limit"), default=20, max_value=100)
	runs = (
		ScrapingRun.objects.select_related("job")
		.order_by("-created_at")[:limit]
	)

	results = []
	for run in runs:
		results.append(
			{
				"id": str(run.id),
				"source_key": run.source_key,
				"status": run.status,
				"job": run.job.key if run.job else None,
				"offers_processed": run.offers_processed,
				"offers_created": run.offers_created,
				"offers_updated": run.offers_updated,
				"offers_unchanged": run.offers_unchanged,
				"offers_flagged_stale": run.offers_flagged_stale,
				"errors_count": run.errors_count,
				"llm_calls_count": run.llm_calls_count,
				"started_at": run.started_at.isoformat() if run.started_at else None,
				"completed_at": run.completed_at.isoformat() if run.completed_at else None,
				"created_at": run.created_at.isoformat(),
			}
		)

	return JsonResponse({"count": len(results), "results": results})


@require_GET
def scraping_run_detail(request, run_id: str):
	try:
		parsed_id = UUID(run_id)
	except ValueError:
		return JsonResponse({"detail": "Invalid run id."}, status=400)

	run = ScrapingRun.objects.select_related("job").filter(id=parsed_id).first()
	if run is None:
		return JsonResponse({"detail": "Scraping run not found."}, status=404)

	return JsonResponse(
		{
			"id": str(run.id),
			"source_key": run.source_key,
			"status": run.status,
			"job": run.job.key if run.job else None,
			"offers_processed": run.offers_processed,
			"offers_created": run.offers_created,
			"offers_updated": run.offers_updated,
			"offers_unchanged": run.offers_unchanged,
			"offers_flagged_stale": run.offers_flagged_stale,
			"offers_deleted": run.offers_deleted,
			"errors_count": run.errors_count,
			"llm_calls_count": run.llm_calls_count,
			"log": run.log,
			"started_at": run.started_at.isoformat() if run.started_at else None,
			"completed_at": run.completed_at.isoformat() if run.completed_at else None,
			"created_at": run.created_at.isoformat(),
			"updated_at": run.updated_at.isoformat(),
		}
	)
