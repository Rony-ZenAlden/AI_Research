from django.urls import path

from .views import IngestUrlView, WebSearchView

urlpatterns = [
    path("web/", WebSearchView.as_view(), name="search_web"),
    path("ingest/url/", IngestUrlView.as_view(), name="search_ingest_url"),
]
