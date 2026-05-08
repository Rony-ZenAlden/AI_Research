from rest_framework import serializers

from .models import SearchQuery


class SearchQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchQuery
        fields = ("id", "kind", "query", "result_count", "duration_ms", "created_at")
        read_only_fields = fields
