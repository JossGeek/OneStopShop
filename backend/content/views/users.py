import json
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from content.models import (
    Domain,
    MatchingHit,
    Offer,
    Organization,
    TargetProfile,
    User,
    UserFavorite,
    UserNeed,
    UserOrganization,
    UserProfile,
    UserRole,
)
from content.views._utils import _parse_positive_int


def _json_error(error: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": error, "message": message}, status=status)


def _parse_body(request) -> dict | None:
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None


def _parse_uuid(value: str, field_name: str) -> UUID | None:
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _get_user_or_response(user_id: str) -> tuple[User | None, JsonResponse | None]:
    parsed_id = _parse_uuid(user_id, "user_id")
    if parsed_id is None:
        return None, _json_error("validation_error", "Invalid user id.", 400)

    user = User.objects.filter(id=parsed_id).first()
    if user is None:
        return None, _json_error("not_found", "User not found.", 404)

    return user, None


def _get_or_create_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _serialize_profile(profile: UserProfile) -> dict:
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


def _serialize_org_link(link: UserOrganization) -> dict:
    return {
        "id": str(link.organization.id),
        "name": link.organization.name,
        "role": link.role.name,
    }


def _serialize_user_detail(user: User) -> dict:
    profile = _get_or_create_profile(user)
    links = list(
        user.organization_links.select_related("organization", "role").order_by("organization__name")
    )
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
        "profile": _serialize_profile(profile),
        "organizations": [_serialize_org_link(link) for link in links],
    }


def _serialize_need(need: UserNeed) -> dict:
    return {
        "id": str(need.id),
        "title": need.title,
        "description": need.description,
        "status": need.status,
        "target_profile_id": str(need.target_profile_id),
        "domain_ids": [str(domain.id) for domain in need.domains.all()],
        "countries": need.countries,
        "matching_hits_count": getattr(need, "matching_hits_count", need.matching_hits.count()),
        "created_at": need.created_at.isoformat(),
        "updated_at": need.updated_at.isoformat(),
    }


def _serialize_offer_preview(offer: Offer) -> dict:
    return {
        "id": str(offer.id),
        "title": offer.title,
        "organization": offer.organization.name,
        "link": offer.link,
    }


def _serialize_favorite(favorite: UserFavorite) -> dict:
    return {
        "id": str(favorite.id),
        "offer": _serialize_offer_preview(favorite.offer),
        "note": favorite.note,
        "created_at": favorite.created_at.isoformat(),
    }


def _serialize_matching_hit(hit: MatchingHit) -> dict:
    return {
        "id": str(hit.id),
        "need": {
            "id": str(hit.need.id),
            "title": hit.need.title,
        },
        "offer": _serialize_offer_preview(hit.offer),
        "match_score": float(hit.match_score),
        "match_reason": hit.match_reason,
        "status": hit.status,
        "created_at": hit.created_at.isoformat(),
        "updated_at": hit.updated_at.isoformat(),
    }


def _paginated_response(request, queryset, serializer, page_size: int, page: int) -> JsonResponse:
    total_count = queryset.count()
    offset = (page - 1) * page_size
    rows = list(queryset[offset:offset + page_size])

    def build_page_url(target_page: int) -> str:
        query = request.GET.copy()
        query["page"] = str(target_page)
        query["page_size"] = str(page_size)
        return request.build_absolute_uri(f"{request.path}?{query.urlencode()}")

    next_url = build_page_url(page + 1) if offset + page_size < total_count else None
    previous_url = build_page_url(page - 1) if page > 1 and total_count else None
    return JsonResponse(
        {
            "count": total_count,
            "next": next_url,
            "previous": previous_url,
            "results": [serializer(row) for row in rows],
        }
    )


def _normalize_countries(values) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("countries must be a list")
    return [str(value).strip().upper() for value in values if str(value).strip()]


def _resolve_domains(domain_ids) -> list[Domain]:
    if domain_ids is None:
        return []
    if not isinstance(domain_ids, list):
        raise ValueError("domain_ids must be a list")

    parsed_ids: list[UUID] = []
    for value in domain_ids:
        parsed = _parse_uuid(str(value), "domain_id")
        if parsed is None:
            raise ValueError("domain_ids contains an invalid UUID")
        parsed_ids.append(parsed)

    domains = list(Domain.objects.filter(id__in=parsed_ids).order_by("name"))
    if len(domains) != len(parsed_ids):
        raise LookupError("One or more domains were not found.")
    return domains


def _resolve_target_profile(target_profile_id: str) -> TargetProfile:
    parsed_id = _parse_uuid(target_profile_id, "target_profile_id")
    if parsed_id is None:
        raise ValueError("target_profile_id is invalid")

    target_profile = TargetProfile.objects.filter(id=parsed_id).first()
    if target_profile is None:
        raise LookupError("Target profile not found.")
    return target_profile


@csrf_exempt
@require_http_methods(["POST"])
def upsert_user(request):
    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    email = str(body.get("email", "")).strip().lower()
    username = str(body.get("username", "")).strip()
    if not email or not username:
        return _json_error("validation_error", "Both email and username are required.", 400)

    profile_data = body.get("profile") or {}
    if not isinstance(profile_data, dict):
        return _json_error("validation_error", "profile must be an object.", 400)

    user = User.objects.filter(email=email).first()
    is_new = user is None
    if is_new:
        try:
            user = User.objects.create(email=email, username=username, password_hash="")
        except IntegrityError:
            return _json_error("conflict", "A user with that email or username already exists.", 409)
        status_code = 201
    else:
        if user.username != username and User.objects.exclude(id=user.id).filter(username=username).exists():
            return _json_error("conflict", "Username is already in use.", 409)
        user.username = username
        user.is_active = True
        user.save(update_fields=["username", "is_active", "updated_at"])
        status_code = 200

    profile = _get_or_create_profile(user)
    if "bio" in profile_data:
        profile.bio = str(profile_data.get("bio") or "")
    if "avatar_url" in profile_data:
        profile.avatar_url = profile_data.get("avatar_url")
    if "preferred_domains" in profile_data:
        profile.preferred_domains = list(profile_data.get("preferred_domains") or [])
    if "preferred_countries" in profile_data:
        profile.preferred_countries = [str(value).upper() for value in profile_data.get("preferred_countries") or []]
    if "notification_enabled" in profile_data:
        profile.notification_enabled = bool(profile_data.get("notification_enabled"))
    profile.save()

    organization_id = body.get("organization_id")
    if organization_id:
        parsed_org_id = _parse_uuid(str(organization_id), "organization_id")
        if parsed_org_id is None:
            return _json_error("validation_error", "Invalid organization id.", 400)
        organization = Organization.objects.filter(id=parsed_org_id).first()
        if organization is None:
            return _json_error("not_found", "Organization not found.", 404)
        if not UserOrganization.objects.filter(user=user, organization=organization).exists():
            role, _ = UserRole.objects.get_or_create(
                name="member",
                defaults={"description": "Default member role"},
            )
            UserOrganization.objects.create(user=user, organization=organization, role=role)

    payload = _serialize_user_detail(user)
    payload["is_new"] = is_new
    return JsonResponse(payload, status=status_code)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def user_resource(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        return JsonResponse(_serialize_user_detail(user))

    if request.method == "DELETE":
        user.is_active = False
        user.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({}, status=204)

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    email = body.get("email")
    username = body.get("username")
    profile_data = body.get("profile")

    if email is not None:
        normalized_email = str(email).strip().lower()
        if not normalized_email:
            return _json_error("validation_error", "email cannot be blank.", 400)
        if User.objects.exclude(id=user.id).filter(email=normalized_email).exists():
            return _json_error("conflict", "Email is already in use.", 409)
        user.email = normalized_email

    if username is not None:
        normalized_username = str(username).strip()
        if not normalized_username:
            return _json_error("validation_error", "username cannot be blank.", 400)
        if User.objects.exclude(id=user.id).filter(username=normalized_username).exists():
            return _json_error("conflict", "Username is already in use.", 409)
        user.username = normalized_username

    user.save()

    if profile_data is not None:
        if not isinstance(profile_data, dict):
            return _json_error("validation_error", "profile must be an object.", 400)
        profile = _get_or_create_profile(user)
        if "bio" in profile_data:
            profile.bio = str(profile_data.get("bio") or "")
        if "avatar_url" in profile_data:
            profile.avatar_url = profile_data.get("avatar_url")
        if "preferred_domains" in profile_data:
            profile.preferred_domains = list(profile_data.get("preferred_domains") or [])
        if "preferred_countries" in profile_data:
            profile.preferred_countries = [str(value).upper() for value in profile_data.get("preferred_countries") or []]
        if "notification_enabled" in profile_data:
            profile.notification_enabled = bool(profile_data.get("notification_enabled"))
        profile.save()

    return JsonResponse(_serialize_user_detail(user))


@csrf_exempt
@require_http_methods(["POST"])
def link_user_organization(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    parsed_org_id = _parse_uuid(str(body.get("organization_id", "")), "organization_id")
    if parsed_org_id is None:
        return _json_error("validation_error", "Invalid organization id.", 400)

    organization = Organization.objects.filter(id=parsed_org_id).first()
    if organization is None:
        return _json_error("not_found", "Organization not found.", 404)

    if UserOrganization.objects.filter(user=user, organization=organization).exists():
        return _json_error("conflict", "User is already linked to that organization.", 409)

    role_name = str(body.get("role") or "member").strip() or "member"
    role, _ = UserRole.objects.get_or_create(
        name=role_name,
        defaults={"description": f"{role_name.title()} role"},
    )
    UserOrganization.objects.create(user=user, organization=organization, role=role)
    return JsonResponse({"id": str(organization.id), "name": organization.name, "role": role.name}, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def unlink_user_organization(request, user_id: str, org_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    parsed_org_id = _parse_uuid(org_id, "org_id")
    if parsed_org_id is None:
        return _json_error("validation_error", "Invalid organization id.", 400)

    deleted, _ = UserOrganization.objects.filter(user=user, organization_id=parsed_org_id).delete()
    if deleted == 0:
        return _json_error("not_found", "Organization link not found.", 404)
    return JsonResponse({}, status=204)


@require_http_methods(["GET"])
def dashboard(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    favorites = list(
        user.favorites.select_related("offer__organization").order_by("-created_at")[:5]
    )
    matches = list(
        user.matching_hits.select_related("need", "offer__organization").order_by("-created_at")[:5]
    )
    payload = {
        "user": _serialize_user_detail(user),
        "stats": {
            "active_needs_count": user.needs.filter(status=UserNeed.NeedStatus.ACTIVE).count(),
            "total_favorites": user.favorites.count(),
            "new_matches_count": user.matching_hits.filter(status=MatchingHit.MatchStatus.NEW).count(),
        },
        "recent_favorites": [_serialize_favorite(favorite) for favorite in favorites],
        "recent_matches": [_serialize_matching_hit(match) for match in matches],
    }
    return JsonResponse(payload)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_needs(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        status_filter = request.GET.get("status", UserNeed.NeedStatus.ACTIVE)
        valid_statuses = {choice for choice, _ in UserNeed.NeedStatus.choices}
        if status_filter not in valid_statuses:
            return _json_error("validation_error", "Invalid need status filter.", 400)

        page = _parse_positive_int(request.GET.get("page"), default=1, max_value=1000000)
        page_size = _parse_positive_int(request.GET.get("page_size"), default=25, max_value=200)
        queryset = (
            user.needs.filter(status=status_filter)
            .select_related("target_profile")
            .prefetch_related("domains")
            .annotate(matching_hits_count=Count("matching_hits"))
            .order_by("-created_at")
        )
        return _paginated_response(request, queryset, _serialize_need, page_size, page)

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    try:
        target_profile = _resolve_target_profile(str(body.get("target_profile_id", "")))
        domains = _resolve_domains(body.get("domain_ids"))
        countries = _normalize_countries(body.get("countries"))
    except ValueError as exc:
        return _json_error("validation_error", str(exc), 400)
    except LookupError as exc:
        return _json_error("not_found", str(exc), 404)

    title = str(body.get("title") or "").strip()
    description = str(body.get("description") or "").strip()
    if not title or not description:
        return _json_error("validation_error", "title and description are required.", 400)

    need = UserNeed.objects.create(
        user=user,
        title=title,
        description=description,
        target_profile=target_profile,
        countries=countries,
    )
    need.domains.set(domains)
    need = UserNeed.objects.select_related("target_profile").prefetch_related("domains").get(id=need.id)
    return JsonResponse(_serialize_need(need), status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def user_need_detail(request, user_id: str, need_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    parsed_need_id = _parse_uuid(need_id, "need_id")
    if parsed_need_id is None:
        return _json_error("validation_error", "Invalid need id.", 400)

    need = (
        UserNeed.objects.filter(id=parsed_need_id, user=user)
        .select_related("target_profile")
        .prefetch_related("domains")
        .first()
    )
    if need is None:
        return _json_error("not_found", "Need not found.", 404)

    if request.method == "DELETE":
        need.delete()
        return JsonResponse({}, status=204)

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    valid_statuses = {choice for choice, _ in UserNeed.NeedStatus.choices}
    status_value = body.get("status", need.status)
    if status_value not in valid_statuses:
        return _json_error("validation_error", "Invalid need status.", 400)

    try:
        target_profile = _resolve_target_profile(str(body.get("target_profile_id", need.target_profile_id)))
        domains = _resolve_domains(body.get("domain_ids"))
        countries = _normalize_countries(body.get("countries"))
    except ValueError as exc:
        return _json_error("validation_error", str(exc), 400)
    except LookupError as exc:
        return _json_error("not_found", str(exc), 404)

    title = str(body.get("title") or "").strip()
    description = str(body.get("description") or "").strip()
    if not title or not description:
        return _json_error("validation_error", "title and description are required.", 400)

    need.title = title
    need.description = description
    need.status = status_value
    need.target_profile = target_profile
    need.countries = countries
    need.save()
    need.domains.set(domains)
    need.refresh_from_db()
    return JsonResponse(_serialize_need(need))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_favorites(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        page = _parse_positive_int(request.GET.get("page"), default=1, max_value=1000000)
        page_size = _parse_positive_int(request.GET.get("page_size"), default=25, max_value=200)
        queryset = user.favorites.select_related("offer__organization").order_by("-created_at")
        return _paginated_response(request, queryset, _serialize_favorite, page_size, page)

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    parsed_offer_id = _parse_uuid(str(body.get("offer_id", "")), "offer_id")
    if parsed_offer_id is None:
        return _json_error("validation_error", "Invalid offer id.", 400)

    offer = Offer.objects.select_related("organization").filter(id=parsed_offer_id).first()
    if offer is None:
        return _json_error("not_found", "Offer not found.", 404)

    if UserFavorite.objects.filter(user=user, offer=offer).exists():
        return _json_error("conflict", "Offer is already favorited.", 409)

    favorite = UserFavorite.objects.create(
        user=user,
        offer=offer,
        note=str(body.get("note") or ""),
    )
    favorite = UserFavorite.objects.select_related("offer__organization").get(id=favorite.id)
    return JsonResponse(_serialize_favorite(favorite), status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def user_favorite_detail(request, user_id: str, offer_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    parsed_offer_id = _parse_uuid(offer_id, "offer_id")
    if parsed_offer_id is None:
        return _json_error("validation_error", "Invalid offer id.", 400)

    deleted, _ = UserFavorite.objects.filter(user=user, offer_id=parsed_offer_id).delete()
    if deleted == 0:
        return _json_error("not_found", "Favorite not found.", 404)
    return JsonResponse({}, status=204)


@require_http_methods(["GET"])
def user_matching_hits(request, user_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    valid_statuses = {choice for choice, _ in MatchingHit.MatchStatus.choices}
    status_filter = request.GET.get("status")
    if status_filter and status_filter not in valid_statuses:
        return _json_error("validation_error", "Invalid match status filter.", 400)

    sort = request.GET.get("sort", "-match_score")
    if sort not in {"-match_score", "created_at"}:
        return _json_error("validation_error", "Invalid matching hit sort.", 400)

    page = _parse_positive_int(request.GET.get("page"), default=1, max_value=1000000)
    page_size = _parse_positive_int(request.GET.get("page_size"), default=25, max_value=200)
    queryset = user.matching_hits.select_related("need", "offer__organization")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    queryset = queryset.order_by(sort)
    return _paginated_response(request, queryset, _serialize_matching_hit, page_size, page)


@csrf_exempt
@require_http_methods(["PATCH"])
def user_matching_hit_detail(request, user_id: str, hit_id: str):
    user, error_response = _get_user_or_response(user_id)
    if error_response is not None:
        return error_response

    parsed_hit_id = _parse_uuid(hit_id, "hit_id")
    if parsed_hit_id is None:
        return _json_error("validation_error", "Invalid matching hit id.", 400)

    hit = (
        MatchingHit.objects.filter(id=parsed_hit_id, user=user)
        .select_related("need", "offer__organization")
        .first()
    )
    if hit is None:
        return _json_error("not_found", "Matching hit not found.", 404)

    body = _parse_body(request)
    if body is None:
        return _json_error("validation_error", "Invalid JSON body.", 400)

    status_value = body.get("status")
    valid_statuses = {
        MatchingHit.MatchStatus.VIEWED,
        MatchingHit.MatchStatus.INTERESTED,
        MatchingHit.MatchStatus.DECLINED,
    }
    if status_value not in valid_statuses:
        return _json_error("validation_error", "Invalid matching hit status.", 400)

    hit.status = status_value
    if hit.viewed_at is None:
        hit.viewed_at = timezone.now()
    hit.save()
    return JsonResponse(_serialize_matching_hit(hit))
