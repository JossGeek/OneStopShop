from django.urls import path

from content import views

urlpatterns = [
    path("", views.api_docs, name="api-docs-home"),
    path("docs", views.api_docs, name="api-docs"),
    path("openapi.json", views.openapi_schema, name="openapi-schema"),
    path("health", views.health, name="health"),
    path("scraping/runs", views.scraping_runs, name="scraping-runs"),
    path("scraping/runs/<str:run_id>", views.scraping_run_detail, name="scraping-run-detail"),
    path("scraping/overview", views.scraping_overview, name="scraping-overview"),
    path("scraping/sources/health", views.scraping_sources_health, name="scraping-sources-health"),
    path("scraping/llm/stats", views.scraping_llm_stats, name="scraping-llm-stats"),
    path("lookups/offer-types", views.offer_types, name="offer-types"),
    path("lookups/domains", views.domains, name="domains"),
    path("lookups/organizations", views.organizations, name="organizations"),
    path("lookups/countries", views.countries, name="countries"),
    path("offers/import/template", views.import_template, name="import-template"),
    path("offers/import/preview", views.import_preview, name="import-preview"),
    path("offers/import/confirm", views.import_confirm, name="import-confirm"),
    path("offers", views.offers, name="offers"),
    path("offers/<str:offer_id>", views.offer_detail, name="offer-detail"),
]
