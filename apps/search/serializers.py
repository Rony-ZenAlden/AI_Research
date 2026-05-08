from rest_framework import serializers

from .scrapers import UnsafeURLError, assert_url_safe


class WebSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=512)
    count = serializers.IntegerField(min_value=1, max_value=30, required=False, default=10)
    categories = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False
    )
    language = serializers.CharField(max_length=8, required=False, default="en")
    time_range = serializers.ChoiceField(
        choices=["", "day", "week", "month", "year"], required=False, default=""
    )


class IngestUrlSerializer(serializers.Serializer):
    url = serializers.URLField()
    title = serializers.CharField(max_length=512, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_url(self, value):
        try:
            assert_url_safe(value)
        except UnsafeURLError as e:
            raise serializers.ValidationError(str(e))
        return value
