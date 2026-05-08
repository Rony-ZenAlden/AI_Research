from django.contrib import admin

from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "source_type", "status", "owner", "chunk_count_display", "created_at")
    list_filter = ("source_type", "status", "created_at")
    search_fields = ("title", "raw_text", "source_uri")
    readonly_fields = ("created_at", "updated_at", "processed_at", "file_size_bytes")

    @admin.display(description="chunks")
    def chunk_count_display(self, obj):
        return obj.chunks.count()


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "position", "char_count", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text",)
    readonly_fields = ("created_at", "embedding")
