from django.urls import path

from .views import (
    DocumentChunksView,
    DocumentDetailView,
    DocumentListView,
    IngestFileView,
    IngestTextView,
    LoadDemoDataView,
    SemanticSearchView,
)

urlpatterns = [
    path("ingest/text/", IngestTextView.as_view(), name="vector_ingest_text"),
    path("ingest/file/", IngestFileView.as_view(), name="vector_ingest_file"),
    path("load-demo/", LoadDemoDataView.as_view(), name="vector_load_demo"),
    path("documents/", DocumentListView.as_view(), name="vector_document_list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="vector_document_detail"),
    path("documents/<int:pk>/chunks/", DocumentChunksView.as_view(), name="vector_document_chunks"),
    path("search/", SemanticSearchView.as_view(), name="vector_semantic_search"),
]
