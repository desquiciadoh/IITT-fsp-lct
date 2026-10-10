"""Matching app URLs."""

from django.urls import path

from matching import views

urlpatterns = [
    path("companies", views.CompanyListCreateView.as_view(), name="company-list-create"),
    path("companies/me", views.CompanyMeView.as_view(), name="company-me"),
    path("positions", views.PositionListCreateView.as_view(), name="position-list-create"),
    path("positions/parse", views.PositionParseView.as_view(), name="position-parse"),
    path("positions/<uuid:pk>", views.PositionDetailView.as_view(), name="position-detail"),
    path("positions/<uuid:pk>/health", views.PositionHealthView.as_view(), name="position-health"),
    path("positions/<uuid:pk>/pool", views.PositionPoolView.as_view(), name="position-pool"),
    path(
        "positions/<uuid:pk>/shortlist",
        views.PositionShortlistListView.as_view(),
        name="position-shortlist-list",
    ),
    path(
        "positions/<uuid:pk>/shortlist/<str:public_id>",
        views.PositionShortlistView.as_view(),
        name="position-shortlist",
    ),
    path("talent/search", views.TalentSearchView.as_view(), name="talent-search"),
    path("talent/<str:public_id>", views.TalentDetailView.as_view(), name="talent-detail"),
    path("talent/<str:public_id>/card.pdf", views.TalentCardPdfView.as_view(), name="talent-card-pdf"),
    # Task BE-17: Vacancies and applications
    path("vacancies", views.VacancyListView.as_view(), name="vacancy-list"),
    path("vacancies/<uuid:pk>", views.VacancyDetailView.as_view(), name="vacancy-detail"),
    path("vacancies/<uuid:pk>/apply", views.ApplyVacancyView.as_view(), name="vacancy-apply"),
    path(
        "candidates/me/applications",
        views.CandidateApplicationListView.as_view(),
        name="candidate-application-list",
    ),
    path(
        "candidates/me/applications/<uuid:pk>/withdraw",
        views.CandidateApplicationWithdrawView.as_view(),
        name="candidate-application-withdraw",
    ),
    path(
        "positions/<uuid:pk>/applications",
        views.PositionApplicationListView.as_view(),
        name="position-application-list",
    ),
    path(
        "positions/<uuid:position_pk>/applications/<uuid:pk>/status",
        views.PositionApplicationStatusView.as_view(),
        name="position-application-status",
    ),
    # Task BE-18: Micro-Tasks
    path("micro-tasks", views.MicroTaskListCreateView.as_view(), name="microtask-list-create"),
    path("micro-tasks/<uuid:pk>", views.MicroTaskDetailView.as_view(), name="microtask-detail"),
    path(
        "micro-tasks/<uuid:pk>/submissions",
        views.MicroTaskSubmissionsListView.as_view(),
        name="microtask-submissions-list",
    ),
    path(
        "micro-tasks/submissions/<uuid:drop_id>/rate",
        views.MicroTaskRateSubmissionView.as_view(),
        name="microtask-rate-submission",
    ),
    path(
        "micro-tasks/submissions/<uuid:drop_id>/prefill-offer",
        views.MicroTaskPrefillOfferView.as_view(),
        name="microtask-prefill-offer",
    ),
    path(
        "candidates/me/micro-tasks",
        views.CandidateMicroTaskListView.as_view(),
        name="candidate-microtask-list",
    ),
    path(
        "candidates/me/micro-tasks/<uuid:drop_id>/submit",
        views.CandidateMicroTaskSubmitView.as_view(),
        name="candidate-microtask-submit",
    ),
]
