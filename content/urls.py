from django.urls import path

from content import views

urlpatterns = [
    path("", views.api_docs, name="api-docs-home"),
    path("docs", views.api_docs, name="api-docs"),
    path("health", views.health, name="health"),
    path("lookups/offer-types", views.offer_types, name="offer-types"),
    path("lookups/domains", views.domains, name="domains"),
    path("offers", views.offers, name="offers"),
    path("offers/<str:offer_id>", views.offer_detail, name="offer-detail"),
]
