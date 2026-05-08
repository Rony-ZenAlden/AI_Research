"""Top-level URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def healthcheck(request):
    return JsonResponse({"status": "ok", "service": "neuroseek-ai"})


api_v1_patterns = [
    path("auth/", include("apps.accounts.urls")),
    path("vector/", include("apps.vector.urls")),
    path("realtime/", include("apps.realtime.urls")),
    path("search/", include("apps.search.urls")),
    path("queries/", include("apps.queries.urls")),
    path("ai/", include("apps.ai.urls")),
    path("research/", include("apps.research.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("api/v1/", include((api_v1_patterns, "v1"))),

    # Frontend (vanilla JS app served from frontend/templates)
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
    path("app/", TemplateView.as_view(template_name="dashboard.html"), name="dashboard"),
    path("app/research/", TemplateView.as_view(template_name="research.html"), name="research"),
    path("login/", TemplateView.as_view(template_name="login.html"), name="login"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
