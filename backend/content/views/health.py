from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from content.views._schema import _openapi_spec


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
            "docs_variant": "swagger",
            "page_title": "OSS API Docs",
        },
    )


@require_GET
def openapi_schema(request):
    return JsonResponse(_openapi_spec())


@require_GET
def redoc_docs(request):
    return render(
        request,
        "content/api_docs.html",
        {
            "schema_url": reverse("openapi-schema"),
            "docs_variant": "redoc",
            "page_title": "OSS API ReDoc",
        },
    )
