"""Outreach URLs."""
from django.urls import path
from outreach import views

urlpatterns = [
    path('offers', views.OfferListCreateView.as_view(), name='offer-list-create'),
    path('offers/<uuid:pk>', views.OfferDetailView.as_view(), name='offer-detail'),
    path('offers/<uuid:pk>/view', views.OfferViewActionView.as_view(), name='offer-view'),
    path('offers/<uuid:pk>/accept', views.OfferAcceptActionView.as_view(), name='offer-accept'),
    path('offers/<uuid:pk>/decline', views.OfferDeclineActionView.as_view(), name='offer-decline'),
    path('offers/<uuid:pk>/withdraw', views.OfferWithdrawActionView.as_view(), name='offer-withdraw'),
    path('events', views.SSEEventsView.as_view(), name='events-sse'),
]
