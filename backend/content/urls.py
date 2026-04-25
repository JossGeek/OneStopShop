from django.urls import path

from content import views

urlpatterns = [
    path("", views.api_docs, name="api-docs-home"),
    path("docs", views.api_docs, name="api-docs"),
    path("redoc", views.redoc_docs, name="api-redoc"),
    path("openapi.json", views.openapi_schema, name="openapi-schema"),
    path("health", views.health, name="health"),
    path("scraping/runs", views.scraping_runs, name="scraping-runs"),
    path("scraping/runs/<str:run_id>", views.scraping_run_detail, name="scraping-run-detail"),
    path("lookups/offer-types", views.offer_types, name="offer-types"),
    path("lookups/domains", views.domains, name="domains"),
    path("lookups/organizations", views.organizations, name="organizations"),
    path("lookups/countries", views.countries, name="countries"),
    path("users", views.upsert_user, name="upsert-user"),
    path("users/<str:user_id>", views.user_resource, name="user-detail"),
    path("users/<str:user_id>/organizations", views.link_user_organization, name="link-user-organization"),
    path("users/<str:user_id>/organizations/<str:org_id>", views.unlink_user_organization, name="unlink-user-organization"),
    path("offers", views.offers, name="offers"),
    path("offers/<str:offer_id>", views.offer_detail, name="offer-detail"),
]
