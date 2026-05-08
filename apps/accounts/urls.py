from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from .views import MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth_register"),
    path("login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("me/", MeView.as_view(), name="auth_me"),
]
