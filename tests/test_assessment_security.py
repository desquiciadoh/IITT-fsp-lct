"""Test Assessment Security: Answer Key NEVER leaks to client.

INVARIANT: The correct answer ('key') is evaluated strictly server-side.
Neither ItemViewSerializer nor any API response may contain 'key' or any
derivative of the correct answer.
"""
from datetime import timedelta

import pytest
from assessment.models import AssessmentItem, AssessmentSession, ItemFamily
from assessment.serializers import AssessmentSessionSerializer, ItemViewSerializer
from core.enums import AssessmentStatus, Grade, Specialization, UserRole
from django.utils import timezone
from identity.models import User


@pytest.fixture
def assessment_item(db):
    user = User.objects.create_user(
        email='tester@example.com',
        password='password123',
        role=UserRole.CANDIDATE,
        email_verified_at=timezone.now(),
    )
    session = AssessmentSession.objects.create(
        candidate=user,
        specialization=Specialization.BACKEND,
        claimed_grade=Grade.MIDDLE,
        status=AssessmentStatus.IN_PROGRESS,
    )
    family, _ = ItemFamily.objects.get_or_create(
        id='be.test.sample.v1',
        defaults={
            'specs': [Specialization.BACKEND],
            'topic': 'sql.basics',
            'format': 'choice',
            'a': 1.0,
            'b': 0.5,
            'c': 0.25,
            'time_limit_s': 90,
        }
    )

    item = AssessmentItem.objects.create(
        assessment=session,
        seq=1,
        family=family,
        seed='test_seed_123',
        view={
            'stem_md': 'What is the result of 2 + 2?',
            'code': {'lang': 'python', 'text': '2 + 2'},
            'options': [
                {'id': 'opt_1', 'text_md': '4'},
                {'id': 'opt_2', 'text_md': '5'},
                {'id': 'opt_3', 'text_md': '3'},
            ],
            'input_type': 'choice',
            'time_limit_s': 90,
        },
        key='opt_1',  # SECRET SERVER-SIDE KEY!
        deadline_at=timezone.now() + timedelta(seconds=90),
    )
    return item, session


@pytest.mark.django_db
class TestAssessmentSecurity:

    def test_item_view_serializer_excludes_key(self, assessment_item):
        """ItemViewSerializer must NEVER include the 'key' field."""
        item, session = assessment_item

        # DB has the key
        assert item.key == 'opt_1'

        # Serializer does NOT have the key
        serializer = ItemViewSerializer(item)
        data = serializer.data

        assert 'key' not in data, "CRITICAL SECURITY BREACH: 'key' found in ItemViewSerializer!"
        assert 'correct_answer' not in data
        assert 'answer_key' not in data

        # Permitted client fields
        assert 'item_id' in data
        assert 'seq' in data
        assert 'stem_md' in data
        assert 'code' in data
        assert 'options' in data
        assert 'deadline_at' in data

    def test_assessment_session_serializer_excludes_key(self, assessment_item):
        """AssessmentSessionSerializer.current must NEVER expose the answer key."""
        item, session = assessment_item

        serializer = AssessmentSessionSerializer(session)
        data = serializer.data

        assert 'current' in data
        current = data['current']
        assert current is not None
        assert 'key' not in current, "CRITICAL: 'key' found in session.current!"
