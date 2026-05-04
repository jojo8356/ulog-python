"""ULog viewer URL routes."""
from __future__ import annotations

from django.urls import path

from .viewer import views

urlpatterns = [
    path("", views.list_view, name="ulog-list"),
    path("r/<int:record_id>/", views.detail_view, name="ulog-detail"),
    path("api/records/", views.api_records, name="ulog-api-records"),
    path("docs/", views.docs_index, name="ulog-docs-index"),
    path("docs/<slug:page>/", views.docs_page, name="ulog-docs-page"),
]
