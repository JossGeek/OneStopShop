from content.views.health import api_docs, health, openapi_schema, redoc_docs
from content.views.imports import import_confirm, import_preview, import_template
from content.views.lookups import countries, domains, offer_types, organizations, target_profiles
from content.views.offers import offer_detail, offers
from content.views.scraping import (
    scraping_llm_stats,
    scraping_overview,
    scraping_run_detail,
    scraping_runs,
    scraping_sources_health,
)
from content.views.users import (
    dashboard,
    link_user_organization,
    unlink_user_organization,
    upsert_user,
    user_favorite_detail,
    user_favorites,
    user_matching_hit_detail,
    user_matching_hits,
    user_need_detail,
    user_needs,
    user_resource,
)

__all__ = [
    "api_docs",
    "health",
    "openapi_schema",
    "redoc_docs",
    "import_confirm",
    "import_preview",
    "import_template",
    "countries",
    "domains",
    "offer_types",
    "organizations",
    "target_profiles",
    "offer_detail",
    "offers",
    "scraping_llm_stats",
    "scraping_overview",
    "scraping_run_detail",
    "scraping_runs",
    "scraping_sources_health",
    "dashboard",
    "link_user_organization",
    "unlink_user_organization",
    "upsert_user",
    "user_favorite_detail",
    "user_favorites",
    "user_matching_hit_detail",
    "user_matching_hits",
    "user_need_detail",
    "user_needs",
    "user_resource",
]
