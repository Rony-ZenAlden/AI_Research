from collections import OrderedDict

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SearchQuery
from .serializers import SearchQuerySerializer

# Show the last N unique queries (deduped on (kind, query)).
RECENT_LIMIT = 15
SCAN_WINDOW = 50


class RecentQueriesView(APIView):
    """GET /api/v1/queries/ — recent unique searches.
    DELETE /api/v1/queries/ — clear all of the caller's search history.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        recent = list(
            SearchQuery.objects.filter(user=request.user)
            .order_by("-created_at")[:SCAN_WINDOW]
        )
        seen = OrderedDict()
        for q in recent:
            key = (q.kind, q.query.strip().lower())
            if key not in seen:
                seen[key] = q
            if len(seen) >= RECENT_LIMIT:
                break
        data = SearchQuerySerializer(list(seen.values()), many=True).data
        return Response({"results": data, "count": len(data)})

    def delete(self, request):
        deleted, _ = SearchQuery.objects.filter(user=request.user).delete()
        return Response({"deleted": deleted}, status=status.HTTP_200_OK)


class SearchQueryDetailView(APIView):
    """DELETE /api/v1/queries/<id>/ — delete one query from history."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            sq = SearchQuery.objects.get(pk=pk, user=request.user)
        except SearchQuery.DoesNotExist:
            return Response({"detail": "not found"}, status=status.HTTP_404_NOT_FOUND)
        sq.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
