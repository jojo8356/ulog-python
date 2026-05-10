"""ULog viewer URL routes."""
from __future__ import annotations

from django.http import HttpResponse
from django.urls import path

from .viewer import views

urlpatterns = [
    path("", views.list_view, name="ulog-list"),
    path("r/<int:record_id>/", views.detail_view, name="ulog-detail"),
    path("api/records/", views.api_records, name="ulog-api-records"),
    # Story 2.9 (FR81) — `git show <sha>` rendered after sha validation.
    path("diff/<str:sha>/", views.diff_view, name="ulog-diff"),
    path("docs/", views.docs_index, name="ulog-docs-index"),
    path("docs/<slug:page>/", views.docs_page, name="ulog-docs-page"),
    # Debug-only QA checklist — visible from the header when the viewer
    # was launched with `ulog-web --debug`. Returns 404 otherwise.
    # State persists in browser localStorage.
    path("_qa/", views.qa_view, name="ulog-qa"),
    # Browser auto-requests /favicon.ico on every page; respond 204
    # rather than 404-spamming the request log.
    path("favicon.ico", lambda r: HttpResponse(status=204), name="ulog-favicon"),
]
