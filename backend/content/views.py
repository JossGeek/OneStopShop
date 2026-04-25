import json
from collections import defaultdict
from datetime import timedelta
from math import ceil
from pathlib import Path
from uuid import UUID

from django.db.models import Count, Max, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from content.models import CrawlUrl, Domain, Offer, OfferType, Organization, ScrapingRun

_WINDOW_DELTAS = {
	"24h": timedelta(hours=24),
	"7d": timedelta(days=7),
	"30d": timedelta(days=30),
}


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


def _run_summary(run: ScrapingRun) -> dict:
	return {
		"id": str(run.id),
		"source_key": run.source_key,
		"status": run.status,
		"offers_processed": run.offers_processed,
		"offers_created": run.offers_created,
		"offers_updated": run.offers_updated,
		"offers_unchanged": run.offers_unchanged,
		"urls_neglected": run.urls_neglected or 0,
		"errors_count": run.errors_count,
		"started_at": run.started_at.isoformat() if run.started_at else None,
		"completed_at": run.completed_at.isoformat() if run.completed_at else None,
		"created_at": run.created_at.isoformat(),
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
							"description": "Scraping run detail with full log",
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
			"/api/scraping/overview": {
				"get": {
					"summary": "Scraping activity overview",
					"parameters": [
						{"name": "window", "in": "query", "schema": {"type": "string", "enum": ["24h", "7d", "30d"]}}
					],
					"responses": {
						"200": {
							"description": "Aggregated scraping stats for time window",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/ScrapingOverviewResponse"}
								}
							},
						}
					},
				}
			},
			"/api/scraping/sources/health": {
				"get": {
					"summary": "Per-source crawl queue health from CrawlUrl table",
					"responses": {
						"200": {
							"description": "URL queue stats per source key",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/SourcesHealthResponse"}
								}
							},
						}
					},
				}
			},
			"/api/scraping/llm/stats": {
				"get": {
					"summary": "LLM extraction method and confidence stats",
					"parameters": [
						{"name": "window", "in": "query", "schema": {"type": "string", "enum": ["24h", "7d", "30d"]}}
					],
					"responses": {
						"200": {
							"description": "Method split and confidence averages",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/LlmStatsResponse"}
								}
							},
						}
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
						"offers_processed": {"type": "integer"},
						"offers_created": {"type": "integer"},
						"offers_updated": {"type": "integer"},
						"offers_unchanged": {"type": "integer"},
						"urls_neglected": {"type": "integer"},
						"errors_count": {"type": "integer"},
						"started_at": {"type": "string", "format": "date-time", "nullable": True},
						"completed_at": {"type": "string", "format": "date-time", "nullable": True},
						"created_at": {"type": "string", "format": "date-time"},
					},
					"required": [
						"id", "source_key", "status", "offers_processed", "offers_created", "offers_updated",
						"offers_unchanged", "urls_neglected", "errors_count", "started_at", "completed_at", "created_at"
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
								"log": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
								"updated_at": {"type": "string", "format": "date-time"},
							},
							"required": ["log", "updated_at"],
						},
					],
				},
				"ScrapingRunTimelineBucket": {
					"type": "object",
					"properties": {
						"bucket": {"type": "string", "format": "date-time"},
						"runs": {"type": "integer"},
						"errors": {"type": "integer"},
					},
					"required": ["bucket", "runs", "errors"],
				},
				"ScrapingOverviewResponse": {
					"type": "object",
					"properties": {
						"window": {"type": "string"},
						"runs_total": {"type": "integer"},
						"runs_success": {"type": "integer"},
						"offers_processed": {"type": "integer"},
						"offers_created": {"type": "integer"},
						"offers_updated": {"type": "integer"},
						"urls_neglected_total": {"type": "integer"},
						"errors_total": {"type": "integer"},
						"runs_timeline": {"type": "array", "items": {"$ref": "#/components/schemas/ScrapingRunTimelineBucket"}},
					},
					"required": [
						"window", "runs_total", "runs_success",
						"offers_processed", "offers_created", "offers_updated",
						"urls_neglected_total", "errors_total", "runs_timeline"
					],
				},
				"SourceHealth": {
					"type": "object",
					"properties": {
						"source_key": {"type": "string"},
						"total_urls": {"type": "integer"},
						"pending": {"type": "integer"},
						"done": {"type": "integer"},
						"error": {"type": "integer"},
						"archived": {"type": "integer"},
						"last_scraped_at": {"type": "string", "format": "date-time", "nullable": True},
					},
					"required": ["source_key", "total_urls", "pending", "done", "error", "archived", "last_scraped_at"],
				},
				"SourcesHealthResponse": {
					"type": "object",
					"properties": {
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/SourceHealth"}},
					},
					"required": ["results"],
				},
				"LlmStatsResponse": {
					"type": "object",
					"properties": {
						"window": {"type": "string"},
						"method_split": {"type": "object", "additionalProperties": {"type": "integer"}},
						"avg_confidence_llm": {"type": "number", "nullable": True},
						"avg_confidence_deterministic": {"type": "number", "nullable": True},
					},
					"required": ["window", "method_split", "avg_confidence_llm", "avg_confidence_deterministic"],
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
	runs = ScrapingRun.objects.order_by("-created_at")[:limit]
	return JsonResponse({"count": len(list(runs)), "results": [_run_summary(r) for r in runs]})


@require_GET
def scraping_run_detail(request, run_id: str):
	try:
		parsed_id = UUID(run_id)
	except ValueError:
		return JsonResponse({"detail": "Invalid run id."}, status=400)

	run = ScrapingRun.objects.filter(id=parsed_id).first()
	if run is None:
		return JsonResponse({"detail": "Scraping run not found."}, status=404)

	data = _run_summary(run)
	data["log"] = run.log
	data["updated_at"] = run.updated_at.isoformat()
	return JsonResponse(data)


@require_GET
def scraping_overview(request):
	window_str = request.GET.get("window", "24h")
	if window_str not in _WINDOW_DELTAS:
		return JsonResponse({"detail": f"Invalid window. Use: {', '.join(_WINDOW_DELTAS)}"}, status=400)

	now = timezone.now()
	since = now - _WINDOW_DELTAS[window_str]
	runs = list(ScrapingRun.objects.filter(created_at__gte=since).order_by("created_at"))

	# Pre-fill every expected bucket with zeros so the chart always has full data.
	if window_str == "24h":
		n_buckets, bucket_hours = 24, 1
	elif window_str == "7d":
		n_buckets, bucket_hours = 7, 24
	else:
		n_buckets, bucket_hours = 30, 24

	bucket_map: dict = {}
	for i in range(n_buckets):
		dt = now - timedelta(hours=bucket_hours * (n_buckets - 1 - i))
		if bucket_hours == 1:
			key = dt.strftime("%Y-%m-%dT%H:00:00Z")
		else:
			key = dt.strftime("%Y-%m-%d")
		bucket_map[key] = {"bucket": key, "runs": 0, "errors": 0}

	for run in runs:
		ts = run.created_at
		key = ts.strftime("%Y-%m-%dT%H:00:00Z") if bucket_hours == 1 else ts.strftime("%Y-%m-%d")
		if key in bucket_map:
			bucket_map[key]["runs"] += 1
			bucket_map[key]["errors"] += run.errors_count

	return JsonResponse({
		"window": window_str,
		"runs_total": len(runs),
		"runs_success": sum(1 for r in runs if r.status == "success"),
		"offers_processed": sum(r.offers_processed for r in runs),
		"offers_created": sum(r.offers_created for r in runs),
		"offers_updated": sum(r.offers_updated for r in runs),
		"urls_neglected_total": sum(r.urls_neglected or 0 for r in runs),
		"errors_total": sum(r.errors_count for r in runs),
		"runs_timeline": list(bucket_map.values()),
	})


@require_GET
def scraping_sources_health(request):
	rows = list(
		CrawlUrl.objects.values("source_key", "status").annotate(count=Count("id"))
	)
	last_scraped = dict(
		CrawlUrl.objects.values("source_key").annotate(ts=Max("last_scraped_at")).values_list("source_key", "ts")
	)

	source_stats: dict = {}
	for row in rows:
		key = row["source_key"]
		if key not in source_stats:
			source_stats[key] = {"pending": 0, "processing": 0, "done": 0, "error": 0, "archived": 0}
		source_stats[key][row["status"]] = row["count"]

	results = []
	for key in sorted(source_stats):
		s = source_stats[key]
		total = sum(s.values())
		ts = last_scraped.get(key)
		results.append({
			"source_key": key,
			"total_urls": total,
			"pending": s.get("pending", 0),
			"done": s.get("done", 0),
			"error": s.get("error", 0),
			"archived": s.get("archived", 0),
			"last_scraped_at": ts.isoformat() if ts else None,
		})

	return JsonResponse({"results": results})


@require_GET
def scraping_llm_stats(request):
	window_str = request.GET.get("window", "24h")
	if window_str not in _WINDOW_DELTAS:
		return JsonResponse({"detail": f"Invalid window. Use: {', '.join(_WINDOW_DELTAS)}"}, status=400)

	since = timezone.now() - _WINDOW_DELTAS[window_str]
	runs = list(ScrapingRun.objects.filter(created_at__gte=since).only("log"))

	method_split: dict = defaultdict(int)
	confidence_llm: list = []
	confidence_det: list = []

	for run in runs:
		for entry in (run.log or []):
			if not isinstance(entry, dict):
				continue
			if entry.get("event") != "url_processed":
				continue
			method = entry.get("method")
			if method:
				method_split[method] += 1
			conf = entry.get("confidence")
			if conf is not None:
				if method in ("llm_primary", "llm_fallback"):
					confidence_llm.append(float(conf))
				elif method == "deterministic":
					confidence_det.append(float(conf))

	return JsonResponse({
		"window": window_str,
		"method_split": dict(method_split),
		"avg_confidence_llm": round(sum(confidence_llm) / len(confidence_llm), 3) if confidence_llm else None,
		"avg_confidence_deterministic": round(sum(confidence_det) / len(confidence_det), 3) if confidence_det else None,
	})


# ── Offer import ──────────────────────────────────────────────────────────────

@require_GET
def import_template(request):
	"""GET /api/offers/import/template — download CSV template."""
	template_path = Path(__file__).parent / "ingestion" / "import_template.csv"
	return FileResponse(
		open(template_path, "rb"),
		as_attachment=True,
		filename="oss_import_template.csv",
		content_type="text/csv",
	)


@csrf_exempt
@require_http_methods(["POST"])
def import_preview(request):
	"""POST /api/offers/import/preview — parse + validate CSV/Excel, no DB writes."""
	from content.ingestion.importer import ImportService  # noqa: PLC0415

	f = request.FILES.get("file")
	if not f:
		return JsonResponse({"error": "No file provided. Send as multipart field 'file'."}, status=400)

	try:
		result = ImportService().preview(f, f.name)
	except Exception as exc:
		return JsonResponse({"error": f"Failed to parse file: {exc}"}, status=400)

	return JsonResponse(result.to_dict())


@csrf_exempt
@require_http_methods(["POST"])
def import_confirm(request):
	"""POST /api/offers/import/confirm — write confirmed valid rows to DB.
	Body: {"rows": [...valid row objects from preview...], "publish": bool}
	"""
	from content.ingestion.importer import ImportService  # noqa: PLC0415

	try:
		body = json.loads(request.body)
	except json.JSONDecodeError:
		return JsonResponse({"error": "Invalid JSON body."}, status=400)

	valid_rows = body.get("rows", [])
	publish = bool(body.get("publish", False))

	if not isinstance(valid_rows, list):
		return JsonResponse({"error": "'rows' must be a list."}, status=400)

	try:
		result = ImportService().confirm(valid_rows, publish)
	except Exception as exc:
		return JsonResponse({"error": f"Import failed: {exc}"}, status=500)

	return JsonResponse(result.to_dict())
