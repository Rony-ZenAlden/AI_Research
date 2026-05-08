from django.urls import path

from .views import RecentQueriesView, SearchQueryDetailView

urlpatterns = [
    path("", RecentQueriesView.as_view(), name="queries_list"),
    path("<int:pk>/", SearchQueryDetailView.as_view(), name="queries_detail"),
]
