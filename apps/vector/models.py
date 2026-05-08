"""Vector store models — Document holds raw content; Chunk stores embeddings."""
import uuid

from django.conf import settings
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


def document_upload_path(instance: "Document", filename: str) -> str:
    """media/documents/<owner_id>/<uuid>.<ext> — opaque to defeat path guessing."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"documents/{instance.owner_id}/{uuid.uuid4().hex}.{ext}"


class Document(models.Model):
    SOURCE_TEXT = "text"
    SOURCE_FILE = "file"
    SOURCE_WEB = "web"
    SOURCE_CHOICES = [
        (SOURCE_TEXT, "Plain text"),
        (SOURCE_FILE, "Uploaded file"),
        (SOURCE_WEB, "Web page"),
    ]

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=512)
    source_type = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_TEXT)
    source_uri = models.CharField(max_length=2048, blank=True)
    raw_text = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    # File upload (null for text/web sources)
    file = models.FileField(upload_to=document_upload_path, null=True, blank=True, max_length=512)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=128, blank=True)

    # Async processing state
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_READY, db_index=True)
    error_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vector_document"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["owner", "status"]),
        ]

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    position = models.PositiveIntegerField()
    text = models.TextField()
    char_count = models.PositiveIntegerField(default=0)
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Postgres-maintained tsvector for keyword search (see migration 0004).
    # Don't write to it from app code — it's a GENERATED column.
    search_vector = SearchVectorField(editable=False, null=True)

    class Meta:
        db_table = "vector_chunk"
        ordering = ["document", "position"]
        constraints = [
            models.UniqueConstraint(fields=["document", "position"], name="uniq_chunk_position_per_doc"),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"Chunk {self.position} of {self.document_id}"
