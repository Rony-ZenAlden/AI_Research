from rest_framework import serializers

from .models import ResearchSession


class ResearchSessionSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchSession
        fields = ("id", "question", "status", "duration_ms", "created_at", "completed_at")
        read_only_fields = fields


class ResearchSessionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchSession
        fields = (
            "id", "question", "status",
            "plan", "document_ids",
            "report_text", "report_sources",
            "error_message", "metadata",
            "duration_ms",
            "created_at", "updated_at", "completed_at",
        )
        read_only_fields = fields


class CreateResearchSessionSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=10, max_length=2000)
