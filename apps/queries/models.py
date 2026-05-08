"""SearchQuery — one row per user search.

We record raw history (no insert-time dedupe) so analytics later can answer
"most searched topics", "search frequency", etc. The list endpoint folds
duplicates for a clean UX.
"""
from django.conf import settings
from django.db import models


class SearchQuery(models.Model):
    KIND_SEMANTIC = "semantic"
    KIND_WEB = "web"
    KIND_CHOICES = [
        (KIND_SEMANTIC, "Semantic"),
        (KIND_WEB, "Web"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_queries",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_SEMANTIC, db_index=True)
    query = models.CharField(max_length=512)
    result_count = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "queries_searchquery"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "kind", "-created_at"]),
        ]
        verbose_name = "Search query"
        verbose_name_plural = "Search queries"

    def __str__(self) -> str:
        return f"[{self.kind}] {self.query[:60]}"
