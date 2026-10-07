"""FSP Sync URLs."""
from django.urls import path
from fsp_sync import views

urlpatterns = [
    path('fsp/link', views.FSPLinkView.as_view(), name='fsp-link'),
    path('fsp/sync', views.FSPSyncTaskTriggerView.as_view(), name='fsp-sync-trigger'),
]
