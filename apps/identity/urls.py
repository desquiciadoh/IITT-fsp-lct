"""Identity app URL patterns."""
from django.urls import path
from identity import views

urlpatterns = [
    path('auth/register', views.RegisterView.as_view(), name='register'),
    path('auth/login', views.LoginView.as_view(), name='login'),
    path('auth/logout', views.LogoutView.as_view(), name='logout'),
    path('me', views.MeView.as_view(), name='me'),
    path('demo/persona', views.DemoPersonaView.as_view(), name='demo-persona'),
    path('demo/time-travel', views.DemoTimeTravelView.as_view(), name='demo-time-travel'),
]
