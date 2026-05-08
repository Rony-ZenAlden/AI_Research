from rest_framework import serializers


class SourceItemSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=512, allow_blank=True)
    ref = serializers.CharField(max_length=2048, allow_blank=True, required=False, default="")
    text = serializers.CharField(max_length=8000)


class SummarizeRequestSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=2, max_length=512)
    mode = serializers.ChoiceField(choices=["summarize", "compare"], default="summarize")
    sources = serializers.ListField(child=SourceItemSerializer(), min_length=1, max_length=20)
