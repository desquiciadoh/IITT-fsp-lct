"""Identity app URL patterns."""
from django.urls import path

from identity import views

urlpatterns = [
    path('auth/csrf', views.CsrfView.as_view(), name='csrf'),
    path('auth/register', views.RegisterView.as_view(), name='register'),
    path('auth/verify-email', views.VerifyEmailView.as_view(), name='verify-email'),
    path('auth/login', views.LoginView.as_view(), name='login'),
    path('auth/logout', views.LogoutView.as_view(), name='logout'),
    path('auth/fsp-id/login', views.FspIdLoginView.as_view(), name='fsp-id-login'),
    path('auth/fsp-id/callback', views.FspIdCallbackView.as_view(), name='fsp-id-callback'),
    path('me', views.MeView.as_view(), name='me'),
    path('demo/persona', views.DemoPersonaView.as_view(), name='demo-persona'),
    path('demo/time-travel', views.DemoTimeTravelView.as_view(), name='demo-time-travel'),
    path('demo/reset', views.DemoResetView.as_view(), name='demo-reset'),
]
