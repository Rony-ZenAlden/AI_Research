from rest_framework import serializers

from .models import Chunk, Document
from .services import SUPPORTED_EXTENSIONS

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class IngestTextSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=512)
    text = serializers.CharField(min_length=10)
    metadata = serializers.JSONField(required=False, default=dict)


class IngestFileSerializer(serializers.Serializer):
    file = serializers.FileField()
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_file(self, f):
        if f.size > MAX_UPLOAD_SIZE_BYTES:
            mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"file exceeds {mb} MB limit")
        ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(sorted(f".{e}" for e in SUPPORTED_EXTENSIONS))
            raise serializers.ValidationError(
                f"unsupported extension '.{ext}'. Allowed: {allowed}"
            )
        return f


class DocumentSummarySerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Document
        fields = (
            "id", "title", "source_type", "source_uri", "status",
            "error_message", "metadata", "chunk_count", "created_at",
        )
        read_only_fields = fields


class DocumentDetailSerializer(serializers.ModelSerializer):
    chunk_count = serializers.IntegerField(read_only=True)
    file_url = serializers.SerializerMethodField()
    raw_text_preview = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id", "title", "source_type", "source_uri", "status",
            "error_message", "metadata", "chunk_count",
            "file_url", "file_size_bytes", "mime_type",
            "raw_text_preview",
            "processed_at", "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url

    def get_raw_text_preview(self, obj):
        if not obj.raw_text:
            return ""
        return obj.raw_text[:2000] + ("…" if len(obj.raw_text) > 2000 else "")


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ("id", "position", "text", "char_count", "metadata")
        read_only_fields = fields


class SearchHitSerializer(serializers.Serializer):
    chunk_id = serializers.IntegerField()
    document_id = serializers.IntegerField()
    document_title = serializers.CharField()
    position = serializers.IntegerField()
    text = serializers.CharField()
    score = serializers.FloatField()                          # 0..1 (cosine sim if available)
    rrf_score = serializers.FloatField(required=False)        # diagnostic
    matched_by = serializers.ListField(child=serializers.CharField(), required=False)

    @classmethod
    def from_chunk(cls, chunk: Chunk, score: float) -> dict:
        return {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "document_title": chunk.document.title,
            "position": chunk.position,
            "text": chunk.text,
            "score": float(score),
        }

    @classmethod
    def from_hybrid_hit(cls, hit) -> dict:
        return {
            "chunk_id": hit.chunk.id,
            "document_id": hit.chunk.document_id,
            "document_title": hit.chunk.document.title,
            "position": hit.chunk.position,
            "text": hit.chunk.text,
            "score": float(hit.score),
            "rrf_score": float(hit.rrf_score),
            "matched_by": list(hit.matched_by),
        }
