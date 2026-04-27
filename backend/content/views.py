import json
from math import ceil
from urllib.parse import urlencode
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from content.models import (
	Domain,
	MatchingHit,
	Offer,
	OfferType,
	Organization,
	ScrapingRun,
	TargetProfile,
	User,
	UserFavorite,
	UserNeed,
	UserOrganization,
	UserProfile,
	UserRole,
)


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


def _error_response(message: str, *, status: int, error: str | None = None, details: dict | None = None) -> JsonResponse:
	payload = {"message": message}
	if error:
		payload["error"] = error
	if details:
		payload["details"] = details
	return JsonResponse(payload, status=status)


def _parse_json_body(request) -> dict | None:
	if not request.body:
		return {}
	try:
		return json.loads(request.body)
	except json.JSONDecodeError:
		return None


def _parse_uuid_or_none(raw_value: str | None) -> UUID | None:
	if raw_value is None:
		return None
	try:
		return UUID(raw_value)
	except ValueError:
		return None


def _get_user_or_error(user_id: str) -> tuple[User | None, JsonResponse | None]:
	parsed_id = _parse_uuid_or_none(user_id)
	if parsed_id is None:
		return None, _error_response("Invalid user id.", status=400, error="validation_error")

	user = User.objects.filter(id=parsed_id).first()
	if user is None:
		return None, _error_response("User not found.", status=404, error="not_found")

	return user, None


def _get_or_create_profile(user: User) -> UserProfile:
	profile, _ = UserProfile.objects.get_or_create(user=user)
	return profile


def _profile_to_dict(profile: UserProfile) -> dict:
	return {
		"id": str(profile.id),
		"user_id": str(profile.user_id),
		"bio": profile.bio,
		"avatar_url": profile.avatar_url,
		"preferred_domains": profile.preferred_domains,
		"preferred_countries": profile.preferred_countries,
		"notification_enabled": profile.notification_enabled,
		"created_at": profile.created_at.isoformat(),
		"updated_at": profile.updated_at.isoformat(),
	}


def _organization_link_to_dict(link: UserOrganization) -> dict:
	return {
		"id": str(link.organization.id),
		"name": link.organization.name,
		"role": link.role.name,
	}


def _offer_preview_to_dict(offer: Offer) -> dict:
	return {
		"id": str(offer.id),
		"title": offer.title,
		"organization": offer.organization.name,
		"link": offer.link,
	}


def _user_to_dict(user: User) -> dict:
	profile = _get_or_create_profile(user)
	organization_links = (
		user.organization_links.select_related("organization", "role")
		.order_by("organization__name", "role__name")
	)
	return {
		"id": str(user.id),
		"username": user.username,
		"email": user.email,
		"is_active": user.is_active,
		"profile": _profile_to_dict(profile),
		"organizations": [_organization_link_to_dict(link) for link in organization_links],
		"created_at": user.created_at.isoformat(),
		"updated_at": user.updated_at.isoformat(),
	}


def _apply_profile_updates(profile: UserProfile, profile_data: dict) -> None:
	# Stage 2 keeps profile updates nested under the user payload so frontend forms
	# can persist both account and profile state with one request.
	if "bio" in profile_data:
		profile.bio = profile_data["bio"] or ""
	if "avatar_url" in profile_data:
		profile.avatar_url = profile_data["avatar_url"] or None
	if "preferred_domains" in profile_data and isinstance(profile_data["preferred_domains"], list):
		profile.preferred_domains = profile_data["preferred_domains"]
	if "preferred_countries" in profile_data and isinstance(profile_data["preferred_countries"], list):
		profile.preferred_countries = profile_data["preferred_countries"]
	if "notification_enabled" in profile_data:
		profile.notification_enabled = bool(profile_data["notification_enabled"])
	profile.save()


def _build_page_url(request, page: int, page_size: int) -> str:
	params = request.GET.copy()
	params["page"] = page
	params["page_size"] = page_size
	return request.build_absolute_uri(f"{request.path}?{urlencode(sorted(params.lists()), doseq=True)}")


def _paginate_queryset(request, queryset, *, default_page_size: int = 10, max_page_size: int = 100) -> tuple[list, dict]:
	page_size = _parse_positive_int(request.GET.get("page_size"), default=default_page_size, max_value=max_page_size)
	page = _parse_positive_int(request.GET.get("page"), default=1, max_value=1000000)
	total_count = queryset.count()
	offset = (page - 1) * page_size
	results = list(queryset[offset:offset + page_size])
	next_url = None
	previous_url = None
	if offset + page_size < total_count:
		next_url = _build_page_url(request, page + 1, page_size)
	if page > 1 and total_count:
		previous_url = _build_page_url(request, page - 1, page_size)
	return results, {
		"count": total_count,
		"next": next_url,
		"previous": previous_url,
	}


def _need_to_dict(need: UserNeed) -> dict:
	return {
		"id": str(need.id),
		"title": need.title,
		"description": need.description,
		"status": need.status,
		"target_profile_id": str(need.target_profile_id),
		"domain_ids": [str(domain.id) for domain in need.domains.all().order_by("name")],
		"countries": need.countries,
		"matching_hits_count": need.matching_hits.count(),
		"created_at": need.created_at.isoformat(),
		"updated_at": need.updated_at.isoformat(),
	}


def _favorite_to_dict(favorite: UserFavorite) -> dict:
	return {
		"id": str(favorite.id),
		"offer": _offer_preview_to_dict(favorite.offer),
		"note": favorite.note or None,
		"created_at": favorite.created_at.isoformat(),
	}


def _matching_hit_to_dict(hit: MatchingHit) -> dict:
	return {
		"id": str(hit.id),
		"need": {
			"id": str(hit.need.id),
			"title": hit.need.title,
		},
		"offer": _offer_preview_to_dict(hit.offer),
		"match_score": float(hit.match_score),
		"match_reason": hit.match_reason,
		"status": hit.status,
		"created_at": hit.created_at.isoformat(),
		"updated_at": hit.updated_at.isoformat(),
	}


def _normalize_countries(value) -> list[str]:
	if not isinstance(value, list):
		return []
	return [str(country).strip().upper() for country in value if str(country).strip()]


def _validate_domain_ids(domain_ids) -> tuple[list[Domain] | None, JsonResponse | None]:
	if not isinstance(domain_ids, list):
		return None, _error_response("domain_ids must be a list of UUIDs.", status=400, error="validation_error")

	parsed_ids = []
	for raw_id in domain_ids:
		parsed = _parse_uuid_or_none(raw_id)
		if parsed is None:
			return None, _error_response("domain_ids must contain valid UUIDs.", status=400, error="validation_error")
		parsed_ids.append(parsed)

	domains = list(Domain.objects.filter(id__in=parsed_ids).order_by("name"))
	if len(domains) != len(set(parsed_ids)):
		return None, _error_response("One or more domains were not found.", status=404, error="not_found")
	return domains, None


def _get_target_profile_or_error(target_profile_id: str | None) -> tuple[TargetProfile | None, JsonResponse | None]:
	parsed_id = _parse_uuid_or_none(target_profile_id)
	if parsed_id is None:
		return None, _error_response("target_profile_id must be a valid UUID.", status=400, error="validation_error")

	target_profile = TargetProfile.objects.filter(id=parsed_id).first()
	if target_profile is None:
		return None, _error_response("Target profile not found.", status=404, error="not_found")
	return target_profile, None


def _get_user_need_or_error(user: User, need_id: str) -> tuple[UserNeed | None, JsonResponse | None]:
	parsed_need_id = _parse_uuid_or_none(need_id)
	if parsed_need_id is None:
		return None, _error_response("Invalid need id.", status=400, error="validation_error")

	need = (
		UserNeed.objects.select_related("target_profile")
		.prefetch_related("domains")
		.filter(id=parsed_need_id, user=user)
		.first()
	)
	if need is None:
		return None, _error_response("Need not found.", status=404, error="not_found")
	return need, None


def _build_stage_zero_paths() -> dict:
	# The live OpenAPI schema must only describe reachable endpoints.
	# Keep stage-zero contract definitions out of the published runtime schema
	# until matching routes/views exist or are exposed as explicit 501 handlers.
	return {}


def _build_stage_zero_planned_paths() -> dict:
	# Stage 0 publishes the future dashboard contract early so frontend work can
	# start before the backing views and models are fully implemented.
	return {
		"/api/users": {
			"post": {
				"tags": ["Users"],
				"summary": "Create or update a user profile",
				"description": "Upsert a user record using the lightweight pre-auth flow planned for stages 2-5.",
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserUpsertRequest"},
							"examples": {
								"default": {
									"value": {
										"email": "john@example.com",
										"username": "john_doe",
										"organization_id": "550e8400-e29b-41d4-a716-446655440000",
									}
								}
							},
						}
					},
				},
				"responses": {
					"200": {
						"description": "Existing user updated",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserUpsertResponse"}
							}
						},
					},
					"201": {
						"description": "New user created",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserUpsertResponse"}
							}
						},
					},
					"400": {
						"description": "Validation error",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			}
		},
		"/api/users/{user_id}": {
			"get": {
				"tags": ["Users"],
				"summary": "Get user profile",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "User profile",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserDetail"}
							}
						},
					},
					"404": {
						"description": "User not found",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			},
			"patch": {
				"tags": ["Users"],
				"summary": "Update a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserUpdateRequest"}
						}
					},
				},
				"responses": {
					"200": {
						"description": "Updated user",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserDetail"}
							}
						},
					},
					"400": {
						"description": "Validation error",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			},
			"delete": {
				"tags": ["Users"],
				"summary": "Soft delete a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"204": {"description": "User marked inactive"},
					"404": {
						"description": "User not found",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			},
		},
		"/api/users/{user_id}/organizations": {
			"post": {
				"tags": ["Users"],
				"summary": "Link a user to an organization",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserOrganizationLinkRequest"}
						}
					},
				},
				"responses": {
					"201": {
						"description": "Organization linked",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserOrganization"}
							}
						},
					},
					"409": {
						"description": "Link already exists",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			}
		},
		"/api/users/{user_id}/organizations/{org_id}": {
			"delete": {
				"tags": ["Users"],
				"summary": "Unlink a user from an organization",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "org_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
				],
				"responses": {
					"204": {"description": "Organization unlinked"},
					"404": {
						"description": "Organization link not found",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			},
		},
		"/api/users/{user_id}/dashboard": {
			"get": {
				"tags": ["Dashboard"],
				"summary": "Get dashboard summary",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "Dashboard summary",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/DashboardResponse"}
							}
						},
					}
				},
			}
		},
		"/api/users/{user_id}/needs": {
			"get": {
				"tags": ["Needs"],
				"summary": "List needs",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "status",
						"in": "query",
						"schema": {"type": "string", "enum": ["active", "fulfilled", "archived"]},
					},
					{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
					{"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
				],
				"responses": {
					"200": {
						"description": "Paginated list of user needs",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserNeedListResponse"}
							}
						},
					}
				},
			},
			"post": {
				"tags": ["Needs"],
				"summary": "Create a need",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserNeedCreateRequest"}
						}
					},
				},
				"responses": {
					"201": {
						"description": "Need created",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserNeed"}
							}
						},
					},
					"400": {
						"description": "Validation error",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			},
		},
		"/api/users/{user_id}/needs/{need_id}": {
			"put": {
				"tags": ["Needs"],
				"summary": "Update a need",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "need_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserNeedUpdateRequest"}
						}
					},
				},
				"responses": {
					"200": {
						"description": "Need updated",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserNeed"}
							}
						},
					}
				},
			},
			"delete": {
				"tags": ["Needs"],
				"summary": "Delete a need",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "need_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
				],
				"responses": {"204": {"description": "Need deleted"}},
			},
		},
		"/api/users/{user_id}/favorites": {
			"get": {
				"tags": ["Favorites"],
				"summary": "List favorites",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
					{"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
				],
				"responses": {
					"200": {
						"description": "Paginated user favorites",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserFavoriteListResponse"}
							}
						},
					}
				},
			},
			"post": {
				"tags": ["Favorites"],
				"summary": "Add a favorite",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/UserFavoriteCreateRequest"}
						}
					},
				},
				"responses": {
					"201": {
						"description": "Favorite created",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserFavorite"}
							}
						},
					}
				},
			},
		},
		"/api/users/{user_id}/favorites/{offer_id}": {
			"delete": {
				"tags": ["Favorites"],
				"summary": "Remove a favorite",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "offer_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
				],
				"responses": {"204": {"description": "Favorite removed"}},
			}
		},
		"/api/users/{user_id}/matching-hits": {
			"get": {
				"tags": ["Matching"],
				"summary": "List matching hits",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "status",
						"in": "query",
						"schema": {"type": "string", "enum": ["new", "viewed", "interested", "declined"]},
					},
					{
						"name": "sort",
						"in": "query",
						"schema": {"type": "string", "enum": ["-match_score", "created_at"]},
					},
					{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
					{"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
				],
				"responses": {
					"200": {
						"description": "Paginated matching hits",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/MatchingHitListResponse"}
							}
						},
					}
				},
			}
		},
		"/api/users/{user_id}/matching-hits/{hit_id}": {
			"patch": {
				"tags": ["Matching"],
				"summary": "Update match status",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
					{
						"name": "hit_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					},
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/MatchingHitUpdateRequest"}
						}
					},
				},
				"responses": {
					"200": {
						"description": "Updated matching hit",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/MatchingHit"}
							}
						},
					}
				},
			}
		},
		"/api/admin/users": {
			"get": {
				"tags": ["Admin"],
				"summary": "List all users",
				"description": "Planned admin endpoint. Authentication is intentionally deferred until Stage 6.",
				"parameters": [
					{"name": "search", "in": "query", "schema": {"type": "string"}},
					{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
					{"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
					{"name": "created_after", "in": "query", "schema": {"type": "string", "format": "date"}},
					{"name": "status", "in": "query", "schema": {"type": "string", "enum": ["active", "inactive", "deleted"]}},
				],
				"responses": {
					"200": {
						"description": "Paginated user list",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserListResponse"}
							}
						},
					},
					"403": {
						"description": "Forbidden",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
							}
						},
					},
				},
			}
		},
		"/api/admin/users/{user_id}": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get a full user profile",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "Detailed user view",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserDetail"}
							}
						},
					}
				},
			},
			"patch": {
				"tags": ["Admin"],
				"summary": "Update a user as admin",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"requestBody": {
					"required": True,
					"content": {
						"application/json": {
							"schema": {"$ref": "#/components/schemas/AdminUserUpdateRequest"}
						}
					},
				},
				"responses": {
					"200": {
						"description": "Updated user",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserDetail"}
							}
						},
					}
				},
			},
			"delete": {
				"tags": ["Admin"],
				"summary": "Hard delete a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {"204": {"description": "User deleted"}},
			},
		},
		"/api/admin/users/{user_id}/profiles": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get a user's profile",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "User profile",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/UserProfile"}
							}
						},
					}
				},
			}
		},
		"/api/admin/users/{user_id}/needs": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get all needs for a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "All user needs",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserNeedListResponse"}
							}
						},
					}
				},
			}
		},
		"/api/admin/users/{user_id}/favorites": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get all favorites for a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "All user favorites",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserFavoriteListResponse"}
							}
						},
					}
				},
			}
		},
		"/api/admin/users/{user_id}/matching-hits": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get all matching hits for a user",
				"parameters": [
					{
						"name": "user_id",
						"in": "path",
						"required": True,
						"schema": {"type": "string", "format": "uuid"},
					}
				],
				"responses": {
					"200": {
						"description": "All matching hits",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminMatchingHitListResponse"}
							}
						},
					}
				},
			}
		},
		"/api/admin/dashboard/analytics": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get system analytics",
				"parameters": [
					{"name": "date_from", "in": "query", "schema": {"type": "string", "format": "date"}},
					{"name": "date_to", "in": "query", "schema": {"type": "string", "format": "date"}},
				],
				"responses": {
					"200": {
						"description": "Analytics response",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminAnalyticsResponse"}
							}
						},
					}
				},
			}
		},
		"/api/admin/dashboard/users-stats": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get user statistics",
				"responses": {
					"200": {
						"description": "User statistics",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminUserStatsResponse"}
							}
						},
					}
				},
			}
		},
		"/api/admin/dashboard/content-stats": {
			"get": {
				"tags": ["Admin"],
				"summary": "Get content statistics",
				"responses": {
					"200": {
						"description": "Content statistics",
						"content": {
							"application/json": {
								"schema": {"$ref": "#/components/schemas/AdminContentStatsResponse"}
							}
						},
					}
				},
			}
		},
	}


def _build_stage_zero_schemas() -> dict:
	return {
		"ApiErrorResponse": {
			"type": "object",
			"properties": {
				"error": {"type": "string", "example": "validation_error"},
				"message": {"type": "string", "example": "Email is required."},
				"details": {"type": "object", "additionalProperties": True},
			},
			"required": ["error", "message"],
		},
		"PaginationEnvelope": {
			"type": "object",
			"properties": {
				"count": {"type": "integer"},
				"next": {"type": "string", "nullable": True},
				"previous": {"type": "string", "nullable": True},
			},
			"required": ["count", "next", "previous"],
		},
		"UserOrganization": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"name": {"type": "string"},
				"role": {"type": "string", "example": "member"},
			},
			"required": ["id", "name", "role"],
		},
		"UserProfile": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"user_id": {"type": "string", "format": "uuid"},
				"bio": {"type": "string"},
				"avatar_url": {"type": "string", "format": "uri", "nullable": True},
				"preferred_domains": {"type": "array", "items": {"type": "string"}},
				"preferred_countries": {"type": "array", "items": {"type": "string"}},
				"notification_enabled": {"type": "boolean"},
				"created_at": {"type": "string", "format": "date-time"},
				"updated_at": {"type": "string", "format": "date-time"},
			},
			"required": [
				"id", "user_id", "bio", "avatar_url", "preferred_domains",
				"preferred_countries", "notification_enabled", "created_at", "updated_at",
			],
		},
		"UserProfileUpdate": {
			"type": "object",
			"properties": {
				"bio": {"type": "string"},
				"avatar_url": {"type": "string", "format": "uri", "nullable": True},
				"preferred_domains": {"type": "array", "items": {"type": "string"}},
				"preferred_countries": {"type": "array", "items": {"type": "string"}},
				"notification_enabled": {"type": "boolean"},
			},
		},
		"UserSummary": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"username": {"type": "string"},
				"email": {"type": "string", "format": "email"},
				"is_active": {"type": "boolean"},
				"created_at": {"type": "string", "format": "date-time"},
				"updated_at": {"type": "string", "format": "date-time"},
			},
			"required": ["id", "username", "email", "is_active", "created_at", "updated_at"],
		},
		"UserDetail": {
			"allOf": [
				{"$ref": "#/components/schemas/UserSummary"},
				{
					"type": "object",
					"properties": {
						"profile": {"$ref": "#/components/schemas/UserProfile"},
						"organizations": {
							"type": "array",
							"items": {"$ref": "#/components/schemas/UserOrganization"},
						},
					},
					"required": ["profile", "organizations"],
				},
			],
		},
		"UserUpsertRequest": {
			"type": "object",
			"properties": {
				"email": {"type": "string", "format": "email"},
				"username": {"type": "string"},
				"organization_id": {"type": "string", "format": "uuid", "nullable": True},
				"profile": {"$ref": "#/components/schemas/UserProfileUpdate"},
			},
			"required": ["email", "username"],
		},
		"UserUpdateRequest": {
			"type": "object",
			"properties": {
				"email": {"type": "string", "format": "email"},
				"username": {"type": "string"},
				"profile": {"$ref": "#/components/schemas/UserProfileUpdate"},
			},
		},
		"UserOrganizationLinkRequest": {
			"type": "object",
			"properties": {
				"organization_id": {"type": "string", "format": "uuid"},
				"role": {"type": "string", "example": "member"},
			},
			"required": ["organization_id"],
		},
		"UserUpsertResponse": {
			"allOf": [
				{"$ref": "#/components/schemas/UserDetail"},
				{
					"type": "object",
					"properties": {"is_new": {"type": "boolean"}},
					"required": ["is_new"],
				},
			],
		},
		"DashboardStats": {
			"type": "object",
			"properties": {
				"active_needs_count": {"type": "integer"},
				"total_favorites": {"type": "integer"},
				"new_matches_count": {"type": "integer"},
			},
			"required": ["active_needs_count", "total_favorites", "new_matches_count"],
		},
		"NeedSummary": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"title": {"type": "string"},
			},
			"required": ["id", "title"],
		},
		"UserNeed": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"title": {"type": "string"},
				"description": {"type": "string"},
				"status": {"type": "string", "enum": ["active", "fulfilled", "archived"]},
				"target_profile_id": {"type": "string", "format": "uuid"},
				"domain_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
				"countries": {"type": "array", "items": {"type": "string"}},
				"matching_hits_count": {"type": "integer"},
				"created_at": {"type": "string", "format": "date-time"},
				"updated_at": {"type": "string", "format": "date-time"},
			},
			"required": [
				"id", "title", "description", "status", "target_profile_id",
				"domain_ids", "countries", "matching_hits_count", "created_at", "updated_at",
			],
		},
		"UserNeedCreateRequest": {
			"type": "object",
			"properties": {
				"title": {"type": "string"},
				"description": {"type": "string"},
				"target_profile_id": {"type": "string", "format": "uuid"},
				"domain_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
				"countries": {"type": "array", "items": {"type": "string"}},
			},
			"required": ["title", "description", "target_profile_id", "domain_ids", "countries"],
		},
		"UserNeedUpdateRequest": {
			"type": "object",
			"properties": {
				"title": {"type": "string"},
				"description": {"type": "string"},
				"status": {"type": "string", "enum": ["active", "fulfilled", "archived"]},
				"target_profile_id": {"type": "string", "format": "uuid"},
				"domain_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}},
				"countries": {"type": "array", "items": {"type": "string"}},
			},
			"required": ["title", "description", "target_profile_id", "domain_ids", "countries"],
		},
		"UserNeedListResponse": {
			"allOf": [
				{"$ref": "#/components/schemas/PaginationEnvelope"},
				{
					"type": "object",
					"properties": {
						"results": {
							"type": "array",
							"items": {"$ref": "#/components/schemas/UserNeed"},
						}
					},
					"required": ["results"],
				},
			],
		},
		"OfferPreview": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"title": {"type": "string"},
				"organization": {"type": "string"},
				"link": {"type": "string", "format": "uri"},
			},
			"required": ["id", "title", "organization", "link"],
		},
		"UserFavorite": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"offer": {"$ref": "#/components/schemas/OfferPreview"},
				"note": {"type": "string", "nullable": True},
				"created_at": {"type": "string", "format": "date-time"},
			},
			"required": ["id", "offer", "note", "created_at"],
		},
		"UserFavoriteCreateRequest": {
			"type": "object",
			"properties": {
				"offer_id": {"type": "string", "format": "uuid"},
				"note": {"type": "string", "nullable": True},
			},
			"required": ["offer_id"],
		},
		"UserFavoriteListResponse": {
			"allOf": [
				{"$ref": "#/components/schemas/PaginationEnvelope"},
				{
					"type": "object",
					"properties": {
						"results": {
							"type": "array",
							"items": {"$ref": "#/components/schemas/UserFavorite"},
						}
					},
					"required": ["results"],
				},
			],
		},
		"MatchingHit": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"need": {"$ref": "#/components/schemas/NeedSummary"},
				"offer": {"$ref": "#/components/schemas/OfferPreview"},
				"match_score": {"type": "number", "format": "float"},
				"match_reason": {"type": "string"},
				"status": {"type": "string", "enum": ["new", "viewed", "interested", "declined"]},
				"created_at": {"type": "string", "format": "date-time"},
				"updated_at": {"type": "string", "format": "date-time"},
			},
			"required": [
				"id", "need", "offer", "match_score", "match_reason",
				"status", "created_at", "updated_at",
			],
		},
		"MatchingHitListResponse": {
			"allOf": [
				{"$ref": "#/components/schemas/PaginationEnvelope"},
				{
					"type": "object",
					"properties": {
						"results": {
							"type": "array",
							"items": {"$ref": "#/components/schemas/MatchingHit"},
						}
					},
					"required": ["results"],
				},
			],
		},
		"MatchingHitUpdateRequest": {
			"type": "object",
			"properties": {
				"status": {"type": "string", "enum": ["viewed", "interested", "declined"]},
			},
			"required": ["status"],
		},
		"DashboardResponse": {
			"type": "object",
			"properties": {
				"user": {"$ref": "#/components/schemas/UserDetail"},
				"stats": {"$ref": "#/components/schemas/DashboardStats"},
				"recent_favorites": {
					"type": "array",
					"items": {"$ref": "#/components/schemas/UserFavorite"},
				},
				"recent_matches": {
					"type": "array",
					"items": {"$ref": "#/components/schemas/MatchingHit"},
				},
			},
			"required": ["user", "stats", "recent_favorites", "recent_matches"],
		},
		"AdminAccountStats": {
			"type": "object",
			"properties": {
				"needs_count": {"type": "integer"},
				"favorites_count": {"type": "integer"},
				"offers_created": {"type": "integer"},
				"last_login": {"type": "string", "format": "date-time", "nullable": True},
			},
			"required": ["needs_count", "favorites_count", "offers_created", "last_login"],
		},
		"AdminUserDetail": {
			"allOf": [
				{"$ref": "#/components/schemas/UserDetail"},
				{
					"type": "object",
					"properties": {
						"password_hash": {"type": "string", "example": "***"},
						"account_stats": {"$ref": "#/components/schemas/AdminAccountStats"},
					},
					"required": ["password_hash", "account_stats"],
				},
			],
		},
		"AdminUserUpdateRequest": {
			"type": "object",
			"properties": {
				"username": {"type": "string"},
				"email": {"type": "string", "format": "email"},
				"is_active": {"type": "boolean"},
			},
		},
		"AdminUserListResponse": {
			"allOf": [
				{"$ref": "#/components/schemas/PaginationEnvelope"},
				{
					"type": "object",
					"properties": {
						"results": {
							"type": "array",
							"items": {"$ref": "#/components/schemas/UserSummary"},
						}
					},
					"required": ["results"],
				},
			],
		},
		"AdminUserNeed": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"title": {"type": "string"},
				"status": {"type": "string", "enum": ["active", "fulfilled", "archived"]},
				"domains": {"type": "array", "items": {"type": "string"}},
				"created_at": {"type": "string", "format": "date-time"},
				"matching_hits_count": {"type": "integer"},
			},
			"required": ["id", "title", "status", "domains", "created_at", "matching_hits_count"],
		},
		"AdminUserNeedListResponse": {
			"type": "object",
			"properties": {
				"count": {"type": "integer"},
				"results": {"type": "array", "items": {"$ref": "#/components/schemas/AdminUserNeed"}},
			},
			"required": ["count", "results"],
		},
		"AdminUserFavorite": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"offer_id": {"type": "string", "format": "uuid"},
				"offer": {"$ref": "#/components/schemas/OfferPreview"},
				"note": {"type": "string", "nullable": True},
				"created_at": {"type": "string", "format": "date-time"},
			},
			"required": ["id", "offer_id", "offer", "note", "created_at"],
		},
		"AdminUserFavoriteListResponse": {
			"type": "object",
			"properties": {
				"count": {"type": "integer"},
				"results": {"type": "array", "items": {"$ref": "#/components/schemas/AdminUserFavorite"}},
			},
			"required": ["count", "results"],
		},
		"AdminMatchingHit": {
			"type": "object",
			"properties": {
				"id": {"type": "string", "format": "uuid"},
				"need_id": {"type": "string", "format": "uuid"},
				"need_title": {"type": "string"},
				"offer_id": {"type": "string", "format": "uuid"},
				"offer_title": {"type": "string"},
				"match_score": {"type": "number", "format": "float"},
				"status": {"type": "string", "enum": ["new", "viewed", "interested", "declined"]},
				"created_at": {"type": "string", "format": "date-time"},
			},
			"required": [
				"id", "need_id", "need_title", "offer_id", "offer_title",
				"match_score", "status", "created_at",
			],
		},
		"AdminMatchingHitListResponse": {
			"type": "object",
			"properties": {
				"count": {"type": "integer"},
				"results": {"type": "array", "items": {"$ref": "#/components/schemas/AdminMatchingHit"}},
			},
			"required": ["count", "results"],
		},
		"AnalyticsPeriod": {
			"type": "object",
			"properties": {
				"from": {"type": "string", "format": "date"},
				"to": {"type": "string", "format": "date"},
			},
			"required": ["from", "to"],
		},
		"AdminAnalyticsUserMetrics": {
			"type": "object",
			"properties": {
				"total_users": {"type": "integer"},
				"active_users": {"type": "integer"},
				"new_users": {"type": "integer"},
				"deleted_users": {"type": "integer"},
			},
			"required": ["total_users", "active_users", "new_users", "deleted_users"],
		},
		"AdminAnalyticsContentMetrics": {
			"type": "object",
			"properties": {
				"total_needs": {"type": "integer"},
				"active_needs": {"type": "integer"},
				"fulfilled_needs": {"type": "integer"},
				"total_favorites": {"type": "integer"},
				"total_matches": {"type": "integer"},
			},
			"required": [
				"total_needs", "active_needs", "fulfilled_needs",
				"total_favorites", "total_matches",
			],
		},
		"AdminAnalyticsEngagementMetrics": {
			"type": "object",
			"properties": {
				"avg_needs_per_user": {"type": "number", "format": "float"},
				"avg_favorites_per_user": {"type": "number", "format": "float"},
				"match_acceptance_rate": {"type": "number", "format": "float"},
				"need_fulfillment_rate": {"type": "number", "format": "float"},
			},
			"required": [
				"avg_needs_per_user", "avg_favorites_per_user",
				"match_acceptance_rate", "need_fulfillment_rate",
			],
		},
		"AdminAnalyticsResponse": {
			"type": "object",
			"properties": {
				"period": {"$ref": "#/components/schemas/AnalyticsPeriod"},
				"user_metrics": {"$ref": "#/components/schemas/AdminAnalyticsUserMetrics"},
				"content_metrics": {"$ref": "#/components/schemas/AdminAnalyticsContentMetrics"},
				"engagement_metrics": {"$ref": "#/components/schemas/AdminAnalyticsEngagementMetrics"},
			},
			"required": ["period", "user_metrics", "content_metrics", "engagement_metrics"],
		},
		"AdminUserStatsByStatus": {
			"type": "object",
			"additionalProperties": {"type": "integer"},
		},
		"AdminUserStatsByOrganization": {
			"type": "object",
			"additionalProperties": {
				"type": "object",
				"properties": {
					"count": {"type": "integer"},
					"active": {"type": "integer"},
				},
				"required": ["count", "active"],
			},
		},
		"AdminGrowthMetrics": {
			"type": "object",
			"properties": {
				"last_7_days": {"type": "integer"},
				"last_30_days": {"type": "integer"},
				"trend": {"type": "string", "enum": ["up", "down", "flat"]},
			},
			"required": ["last_7_days", "last_30_days", "trend"],
		},
		"AdminUserStatsResponse": {
			"type": "object",
			"properties": {
				"total_users": {"type": "integer"},
				"active_users": {"type": "integer"},
				"inactive_users": {"type": "integer"},
				"by_status": {"$ref": "#/components/schemas/AdminUserStatsByStatus"},
				"by_organization": {"$ref": "#/components/schemas/AdminUserStatsByOrganization"},
				"growth": {"$ref": "#/components/schemas/AdminGrowthMetrics"},
			},
			"required": [
				"total_users", "active_users", "inactive_users",
				"by_status", "by_organization", "growth",
			],
		},
		"AdminNeedsStats": {
			"type": "object",
			"properties": {
				"total": {"type": "integer"},
				"active": {"type": "integer"},
				"fulfilled": {"type": "integer"},
				"archived": {"type": "integer"},
				"by_domain": {"type": "object", "additionalProperties": {"type": "integer"}},
			},
			"required": ["total", "active", "fulfilled", "archived", "by_domain"],
		},
		"AdminFavoritesStats": {
			"type": "object",
			"properties": {
				"total": {"type": "integer"},
				"unique_offers": {"type": "integer"},
				"avg_per_user": {"type": "number", "format": "float"},
			},
			"required": ["total", "unique_offers", "avg_per_user"],
		},
		"AdminMatchingDistribution": {
			"type": "object",
			"properties": {
				"excellent": {"type": "integer"},
				"good": {"type": "integer"},
				"fair": {"type": "integer"},
			},
			"required": ["excellent", "good", "fair"],
		},
		"AdminMatchingStats": {
			"type": "object",
			"properties": {
				"total_matches": {"type": "integer"},
				"avg_score": {"type": "number", "format": "float"},
				"score_distribution": {"$ref": "#/components/schemas/AdminMatchingDistribution"},
			},
			"required": ["total_matches", "avg_score", "score_distribution"],
		},
		"AdminContentStatsResponse": {
			"type": "object",
			"properties": {
				"needs": {"$ref": "#/components/schemas/AdminNeedsStats"},
				"favorites": {"$ref": "#/components/schemas/AdminFavoritesStats"},
				"matching": {"$ref": "#/components/schemas/AdminMatchingStats"},
			},
			"required": ["needs", "favorites", "matching"],
		},
	}


def _openapi_spec() -> dict:
	stage_zero_paths = _build_stage_zero_paths()
	stage_zero_schemas = _build_stage_zero_schemas()
	return {
		"openapi": "3.0.3",
		"info": {
			"title": "SUNRISE OSS API",
			"version": "1.1.0-stage0",
			"description": (
				"Stage 0 contract for current OSS endpoints plus the planned user dashboard and "
				"admin APIs needed for frontend-first development."
			),
		},
		"servers": [{"url": "/"}],
		"tags": [
			{"name": "System", "description": "Operational and documentation endpoints"},
			{"name": "Lookups", "description": "Offer lookup datasets"},
			{"name": "Offers", "description": "Current offer catalogue endpoints"},
			{"name": "Scraping", "description": "Current scraping telemetry endpoints"},
			{"name": "Users", "description": "Planned user management endpoints"},
			{"name": "Dashboard", "description": "Planned user dashboard endpoints"},
			{"name": "Needs", "description": "Planned need management endpoints"},
			{"name": "Favorites", "description": "Planned favorite endpoints"},
			{"name": "Matching", "description": "Planned matching-hit endpoints"},
			{"name": "Admin", "description": "Planned admin-only endpoints for Stage 6+"},
		],
		"paths": {
			"/api/health": {
				"get": {
					"tags": ["System"],
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
					"tags": ["Lookups"],
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
					"tags": ["Lookups"],
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
					"tags": ["Lookups"],
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
			"/api/lookups/target-profiles": {
				"get": {
					"tags": ["Lookups"],
					"summary": "List target profiles",
					"responses": {
						"200": {
							"description": "Target profile lookup entries",
							"content": {
								"application/json": {
									"schema": {"$ref": "#/components/schemas/TargetProfileLookupResponse"}
								}
							},
						}
					},
				}
			},
			"/api/lookups/countries": {
				"get": {
					"tags": ["Lookups"],
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
					"tags": ["Offers"],
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
					"tags": ["Offers"],
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
					"tags": ["Scraping"],
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
					"tags": ["Scraping"],
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
			"/api/docs": {
				"get": {
					"tags": ["System"],
					"summary": "Swagger UI documentation",
					"responses": {"200": {"description": "HTML documentation page"}},
				}
			},
			"/api/redoc": {
				"get": {
					"tags": ["System"],
					"summary": "ReDoc documentation",
					"responses": {"200": {"description": "HTML documentation page"}},
				}
			},
			**stage_zero_paths,
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
				"TargetProfileLookup": {
					"type": "object",
					"properties": {
						"id": {"type": "string", "format": "uuid"},
						"name": {"type": "string"},
						"description": {"type": "string"},
					},
					"required": ["id", "name", "description"],
				},
				"TargetProfileLookupResponse": {
					"type": "object",
					"properties": {
						"count": {"type": "integer"},
						"results": {"type": "array", "items": {"$ref": "#/components/schemas/TargetProfileLookup"}},
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
				**stage_zero_schemas,
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
		{
			"schema_url": reverse("openapi-schema"),
			"page_title": "SUNRISE OSS Swagger UI",
			"docs_variant": "swagger",
		},
	)


@require_GET
def redoc_docs(request):
	return render(
		request,
		"content/api_docs.html",
		{
			"schema_url": reverse("openapi-schema"),
			"page_title": "SUNRISE OSS ReDoc",
			"docs_variant": "redoc",
		},
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
def target_profiles(request):
	data = list(TargetProfile.objects.order_by("name").values("id", "name", "description"))
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


@csrf_exempt
@require_http_methods(["POST"])
def upsert_user(request):
	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	email = (data.get("email") or "").strip().lower()
	username = (data.get("username") or "").strip()
	if not email or not username:
		return _error_response(
			"Email and username are required.",
			status=400,
			error="validation_error",
			details={
				"email": ["This field is required."] if not email else [],
				"username": ["This field is required."] if not username else [],
			},
		)

	organization_id = data.get("organization_id")
	organization = None
	if organization_id:
		parsed_org_id = _parse_uuid_or_none(organization_id)
		if parsed_org_id is None:
			return _error_response("organization_id must be a valid UUID.", status=400, error="validation_error")
		organization = Organization.objects.filter(id=parsed_org_id).first()
		if organization is None:
			return _error_response("Organization not found.", status=404, error="not_found")

	try:
		user, created = User.objects.update_or_create(
			email=email,
			defaults={"username": username, "is_active": True},
		)
	except IntegrityError:
		return _error_response("A user with those details already exists.", status=409, error="conflict")

	profile = _get_or_create_profile(user)
	if isinstance(data.get("profile"), dict):
		_apply_profile_updates(profile, data["profile"])

	if organization is not None:
		role, _ = UserRole.objects.get_or_create(
			name="member",
			defaults={"description": "Default member role for Stage 2 organization links."},
		)
		UserOrganization.objects.get_or_create(user=user, organization=organization, role=role)

	payload = _user_to_dict(User.objects.get(id=user.id))
	payload["is_new"] = created
	return JsonResponse(payload, status=201 if created else 200)


@require_GET
def user_detail(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error
	return JsonResponse(_user_to_dict(user))


@csrf_exempt
@require_http_methods(["PATCH"])
def update_user(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	if "email" in data:
		email = (data.get("email") or "").strip().lower()
		if not email:
			return _error_response("Email cannot be empty.", status=400, error="validation_error")
		user.email = email

	if "username" in data:
		username = (data.get("username") or "").strip()
		if not username:
			return _error_response("Username cannot be empty.", status=400, error="validation_error")
		user.username = username

	try:
		user.save()
	except IntegrityError:
		return _error_response("A user with those details already exists.", status=409, error="conflict")

	if isinstance(data.get("profile"), dict):
		profile = _get_or_create_profile(user)
		_apply_profile_updates(profile, data["profile"])

	return JsonResponse(_user_to_dict(User.objects.get(id=user.id)))


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_user(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	if user.is_active:
		user.is_active = False
		user.save(update_fields=["is_active", "updated_at"])
	return JsonResponse({}, status=204)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def user_resource(request, user_id: str):
	if request.method == "GET":
		return user_detail(request, user_id)
	if request.method == "PATCH":
		return update_user(request, user_id)
	return delete_user(request, user_id)


@csrf_exempt
@require_http_methods(["POST"])
def link_user_organization(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	organization_id = data.get("organization_id")
	parsed_org_id = _parse_uuid_or_none(organization_id)
	if parsed_org_id is None:
		return _error_response("organization_id is required and must be a valid UUID.", status=400, error="validation_error")

	organization = Organization.objects.filter(id=parsed_org_id).first()
	if organization is None:
		return _error_response("Organization not found.", status=404, error="not_found")

	if UserOrganization.objects.filter(user=user, organization=organization).exists():
		return _error_response("User is already linked to this organization.", status=409, error="conflict")

	role_name = (data.get("role") or "member").strip().lower() or "member"
	role, _ = UserRole.objects.get_or_create(
		name=role_name,
		defaults={"description": f"Auto-created Stage 2 role: {role_name}."},
	)
	link = UserOrganization.objects.create(user=user, organization=organization, role=role)
	return JsonResponse(_organization_link_to_dict(link), status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def unlink_user_organization(request, user_id: str, org_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	parsed_org_id = _parse_uuid_or_none(org_id)
	if parsed_org_id is None:
		return _error_response("Invalid organization id.", status=400, error="validation_error")

	links = UserOrganization.objects.filter(user=user, organization_id=parsed_org_id)
	if not links.exists():
		return _error_response("Organization link not found.", status=404, error="not_found")

	links.delete()
	return JsonResponse({}, status=204)


@require_GET
def dashboard(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	recent_favorites = list(
		UserFavorite.objects.select_related("offer", "offer__organization")
		.filter(user=user)
		.order_by("-created_at")[:5]
	)
	recent_matches = list(
		MatchingHit.objects.select_related("need", "offer", "offer__organization")
		.filter(user=user)
		.order_by("-created_at")[:5]
	)

	return JsonResponse(
		{
			"user": _user_to_dict(user),
			"stats": {
				"active_needs_count": UserNeed.objects.filter(user=user, status=UserNeed.NeedStatus.ACTIVE).count(),
				"total_favorites": UserFavorite.objects.filter(user=user).count(),
				"new_matches_count": MatchingHit.objects.filter(user=user, status=MatchingHit.MatchStatus.NEW).count(),
			},
			"recent_favorites": [_favorite_to_dict(favorite) for favorite in recent_favorites],
			"recent_matches": [_matching_hit_to_dict(hit) for hit in recent_matches],
		}
	)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_needs(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	if request.method == "GET":
		status_value = request.GET.get("status", UserNeed.NeedStatus.ACTIVE)
		valid_statuses = {choice for choice, _ in UserNeed.NeedStatus.choices}
		if status_value not in valid_statuses:
			return _error_response("Invalid need status filter.", status=400, error="validation_error")

		queryset = (
			UserNeed.objects.select_related("target_profile")
			.prefetch_related("domains")
			.filter(user=user, status=status_value)
			.order_by("-created_at")
		)
		rows, pagination = _paginate_queryset(request, queryset)
		return JsonResponse(
			{
				**pagination,
				"results": [_need_to_dict(need) for need in rows],
			}
		)

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	title = (data.get("title") or "").strip()
	description = (data.get("description") or "").strip()
	if not title or not description:
		return _error_response("Title and description are required.", status=400, error="validation_error")

	target_profile, target_profile_error = _get_target_profile_or_error(data.get("target_profile_id"))
	if target_profile_error:
		return target_profile_error

	domains, domains_error = _validate_domain_ids(data.get("domain_ids", []))
	if domains_error:
		return domains_error

	need = UserNeed.objects.create(
		user=user,
		title=title,
		description=description,
		target_profile=target_profile,
		countries=_normalize_countries(data.get("countries", [])),
	)
	if domains:
		need.domains.set(domains)

	need = UserNeed.objects.select_related("target_profile").prefetch_related("domains").get(id=need.id)
	return JsonResponse(_need_to_dict(need), status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def user_need_detail(request, user_id: str, need_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	need, need_error = _get_user_need_or_error(user, need_id)
	if need_error:
		return need_error

	if request.method == "DELETE":
		need.delete()
		return JsonResponse({}, status=204)

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	title = (data.get("title") or "").strip()
	description = (data.get("description") or "").strip()
	status_value = data.get("status", need.status)
	if not title or not description:
		return _error_response("Title and description are required.", status=400, error="validation_error")

	valid_statuses = {choice for choice, _ in UserNeed.NeedStatus.choices}
	if status_value not in valid_statuses:
		return _error_response("Invalid need status.", status=400, error="validation_error")

	target_profile, target_profile_error = _get_target_profile_or_error(data.get("target_profile_id"))
	if target_profile_error:
		return target_profile_error

	domains, domains_error = _validate_domain_ids(data.get("domain_ids", []))
	if domains_error:
		return domains_error

	need.title = title
	need.description = description
	need.status = status_value
	need.target_profile = target_profile
	need.countries = _normalize_countries(data.get("countries", []))
	need.save()
	need.domains.set(domains)

	need = UserNeed.objects.select_related("target_profile").prefetch_related("domains").get(id=need.id)
	return JsonResponse(_need_to_dict(need))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_favorites(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	if request.method == "GET":
		queryset = (
			UserFavorite.objects.select_related("offer", "offer__organization")
			.filter(user=user)
			.order_by("-created_at")
		)
		rows, pagination = _paginate_queryset(request, queryset)
		return JsonResponse(
			{
				**pagination,
				"results": [_favorite_to_dict(favorite) for favorite in rows],
			}
		)

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	offer_id = _parse_uuid_or_none(data.get("offer_id"))
	if offer_id is None:
		return _error_response("offer_id is required and must be a valid UUID.", status=400, error="validation_error")

	offer = Offer.objects.select_related("organization").filter(id=offer_id).first()
	if offer is None:
		return _error_response("Offer not found.", status=404, error="not_found")

	try:
		favorite = UserFavorite.objects.create(
			user=user,
			offer=offer,
			note=(data.get("note") or "").strip(),
		)
	except IntegrityError:
		return _error_response("Offer is already in favorites.", status=409, error="conflict")

	return JsonResponse(_favorite_to_dict(favorite), status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def user_favorite_detail(request, user_id: str, offer_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	parsed_offer_id = _parse_uuid_or_none(offer_id)
	if parsed_offer_id is None:
		return _error_response("Invalid offer id.", status=400, error="validation_error")

	favorite = UserFavorite.objects.filter(user=user, offer_id=parsed_offer_id).first()
	if favorite is None:
		return _error_response("Favorite not found.", status=404, error="not_found")

	favorite.delete()
	return JsonResponse({}, status=204)


@require_GET
def user_matching_hits(request, user_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	queryset = MatchingHit.objects.select_related("need", "offer", "offer__organization").filter(user=user)
	status_value = request.GET.get("status")
	if status_value:
		valid_statuses = {choice for choice, _ in MatchingHit.MatchStatus.choices}
		if status_value not in valid_statuses:
			return _error_response("Invalid matching status filter.", status=400, error="validation_error")
		queryset = queryset.filter(status=status_value)

	sort_value = request.GET.get("sort", "-match_score")
	if sort_value not in {"-match_score", "created_at"}:
		return _error_response("Invalid sort value.", status=400, error="validation_error")
	if sort_value == "created_at":
		queryset = queryset.order_by("-created_at")
	else:
		queryset = queryset.order_by("-match_score", "-created_at")

	rows, pagination = _paginate_queryset(request, queryset)
	return JsonResponse(
		{
			**pagination,
			"results": [_matching_hit_to_dict(hit) for hit in rows],
		}
	)


@csrf_exempt
@require_http_methods(["PATCH"])
def user_matching_hit_detail(request, user_id: str, hit_id: str):
	user, error = _get_user_or_error(user_id)
	if error:
		return error

	parsed_hit_id = _parse_uuid_or_none(hit_id)
	if parsed_hit_id is None:
		return _error_response("Invalid hit id.", status=400, error="validation_error")

	hit = (
		MatchingHit.objects.select_related("need", "offer", "offer__organization")
		.filter(id=parsed_hit_id, user=user)
		.first()
	)
	if hit is None:
		return _error_response("Matching hit not found.", status=404, error="not_found")

	data = _parse_json_body(request)
	if data is None:
		return _error_response("Request body must be valid JSON.", status=400, error="validation_error")

	status_value = data.get("status")
	if status_value not in {
		MatchingHit.MatchStatus.VIEWED,
		MatchingHit.MatchStatus.INTERESTED,
		MatchingHit.MatchStatus.DECLINED,
	}:
		return _error_response("Invalid matching hit status.", status=400, error="validation_error")

	hit.status = status_value
	if hit.viewed_at is None:
		hit.viewed_at = timezone.now()
	hit.save()
	return JsonResponse(_matching_hit_to_dict(hit))


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
