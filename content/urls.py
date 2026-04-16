from django.urls import path

from content import views

urlpatterns = [
    path("", views.api_docs, name="api-docs-home"),
    path("docs", views.api_docs, name="api-docs"),
    path("openapi.json", views.openapi_schema, name="openapi-schema"),
    path("health", views.health, name="health"),
    path("scraping/runs", views.scraping_runs, name="scraping-runs"),
    path("scraping/runs/<str:run_id>", views.scraping_run_detail, name="scraping-run-detail"),
    path("lookups/offer-types", views.offer_types, name="offer-types"),
    path("lookups/domains", views.domains, name="domains"),
    path("lookups/organizations", views.organizations, name="organizations"),
    path("lookups/countries", views.countries, name="countries"),
    path("offers", views.offers, name="offers"),
    path("offers/<str:offer_id>", views.offer_detail, name="offer-detail"),
]
