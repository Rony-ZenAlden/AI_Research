from django.contrib import admin

from .models import SearchQuery


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "short_query", "result_count", "duration_ms", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("query", "user__email")
    readonly_fields = ("created_at",)

    @admin.display(description="query")
    def short_query(self, obj):
        return obj.query[:100]
