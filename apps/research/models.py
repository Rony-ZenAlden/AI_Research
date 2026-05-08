"""ResearchSession — one row per multi-step research run."""
from django.conf import settings
from django.db import models


class ResearchSession(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PLANNING = "planning"
    STATUS_SEARCHING = "searching"
    STATUS_FETCHING = "fetching"
    STATUS_RETRIEVING = "retrieving"
    STATUS_SYNTHESIZING = "synthesizing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PLANNING, "Planning"),
        (STATUS_SEARCHING, "Searching"),
        (STATUS_FETCHING, "Fetching"),
        (STATUS_RETRIEVING, "Retrieving"),
        (STATUS_SYNTHESIZING, "Synthesizing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_sessions",
    )
    question = models.CharField(max_length=2000)

    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    plan = models.JSONField(default=dict, blank=True)            # {"queries": ["...", ...]}
    document_ids = models.JSONField(default=list, blank=True)    # docs ingested for this session
    report_text = models.TextField(blank=True)                   # final markdown report
    report_sources = models.JSONField(default=list, blank=True)  # [{index, title, ref}]
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "research_session"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "status"]),
        ]
        verbose_name = "Research session"
        verbose_name_plural = "Research sessions"

    def __str__(self) -> str:
        return f"[{self.status}] {self.question[:80]}"
