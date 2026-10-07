"""Assessment URLs."""
from django.urls import path
from assessment import views

urlpatterns = [
    path('assessments/eligibility', views.EligibilityView.as_view(), name='assessment-eligibility'),
    path('assessments', views.AssessmentListCreateView.as_view(), name='assessment-list-create'),
    path('assessments/<uuid:pk>', views.AssessmentDetailView.as_view(), name='assessment-detail'),
    path('assessments/<uuid:pk>/answers', views.AssessmentAnswerView.as_view(), name='assessment-answer'),
    path('assessments/<uuid:pk>/result', views.AssessmentResultView.as_view(), name='assessment-result'),
]
