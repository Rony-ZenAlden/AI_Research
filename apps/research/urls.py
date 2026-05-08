from django.urls import path

from .views import (
    ResearchExportMarkdownView,
    ResearchExportPdfView,
    ResearchSessionDetailView,
    ResearchSessionListCreateView,
)

urlpatterns = [
    path("sessions/", ResearchSessionListCreateView.as_view(), name="research_sessions"),
    path("sessions/<int:pk>/", ResearchSessionDetailView.as_view(), name="research_session_detail"),
    path("sessions/<int:pk>/export.md", ResearchExportMarkdownView.as_view(), name="research_export_md"),
    path("sessions/<int:pk>/export.pdf", ResearchExportPdfView.as_view(), name="research_export_pdf"),
]
