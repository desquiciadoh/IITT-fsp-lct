import pytest
@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()

@pytest.fixture
def candidate_user(db):
    from identity.models import User
    return User.objects.create_user(email='candidate@example.com', password='password123', role='candidate')

@pytest.fixture
def employer_user(db):
    from identity.models import User
    return User.objects.create_user(email='employer@example.com', password='password123', role='employer')
