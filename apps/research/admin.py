from django.contrib import admin

from .models import ResearchSession


@admin.register(ResearchSession)
class ResearchSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "short_q", "duration_ms", "created_at", "completed_at")
    list_filter = ("status", "created_at")
    search_fields = ("question", "user__email")
    readonly_fields = ("created_at", "updated_at", "completed_at", "duration_ms",
                       "plan", "document_ids", "report_sources")

    @admin.display(description="question")
    def short_q(self, obj):
        return obj.question[:100]
