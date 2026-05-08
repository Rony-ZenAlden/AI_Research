from django.urls import path

from .views import TestPingView

urlpatterns = [
    path("test-ping/", TestPingView.as_view(), name="realtime_test_ping"),
]
