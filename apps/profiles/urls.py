"""Profiles URLs."""

from django.urls import path

from profiles import views

urlpatterns = [
    path("taxonomy", views.TaxonomyView.as_view(), name="taxonomy"),
    path("candidates/me", views.CandidateMeView.as_view(), name="candidate-me"),
    path("candidates/me/grants", views.CandidateGrantsListView.as_view(), name="candidate-grants-list"),
    path("candidates/me/grants/<uuid:pk>/revoke", views.CandidateGrantRevokeView.as_view(), name="candidate-grant-revoke"),
    path("candidates/me/consents", views.ConsentsView.as_view(), name="candidate-consents"),
    path("candidates/me/card.pdf", views.PlayerCardPdfView.as_view(), name="candidate-card-pdf"),
    path("candidates/me/resume", views.ResumeParseView.as_view(), name="candidate-resume"),
    path("verify/<str:public_id>", views.VerifyPublicIdView.as_view(), name="verify-public-id"),
]
