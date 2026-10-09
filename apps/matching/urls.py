"""Matching app URLs."""
from django.urls import path
from matching import views

urlpatterns = [
    path('companies', views.CompanyListCreateView.as_view(), name='company-list-create'),
    path('companies/me', views.CompanyMeView.as_view(), name='company-me'),
    path('positions', views.PositionListCreateView.as_view(), name='position-list-create'),
    path('positions/parse', views.PositionParseView.as_view(), name='position-parse'),
    path('positions/<uuid:pk>', views.PositionDetailView.as_view(), name='position-detail'),
    path('positions/<uuid:pk>/pool', views.PositionPoolView.as_view(), name='position-pool'),
    path('positions/<uuid:pk>/shortlist', views.PositionShortlistListView.as_view(), name='position-shortlist-list'),
    path('positions/<uuid:pk>/shortlist/<str:public_id>', views.PositionShortlistView.as_view(), name='position-shortlist'),
    path('talent/search', views.TalentSearchView.as_view(), name='talent-search'),
    path('talent/<str:public_id>', views.TalentDetailView.as_view(), name='talent-detail'),
]
