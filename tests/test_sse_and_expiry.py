"""SSE tenant scoping, on-commit publishing, and lazy offer expiry."""
from datetime import timedelta

import pytest
from core.enums import ContactChannel, OfferStatus, SalaryType, UserRole
from core.errors import InvalidTransition, OfferExpired, VersionConflict
from django.db import transaction
from django.utils import timezone
from identity.models import AuditLog, User
from matching.models import Company, CompanyMember, Position
from outreach.events import (
    _RECENT_EVENTS,
    publish_domain_event,
    register_subscriber,
    unregister_subscriber,
)
from outreach.models import Offer, OfferEvent
from outreach.services import OfferService
from rest_framework.test import APIClient


def _drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.fixture
def world(db):
    _RECENT_EVENTS.clear()
    cand_a = User.objects.create_user(email='a@example.com', password='pw12345678', role=UserRole.CANDIDATE)
    cand_b = User.objects.create_user(email='b@example.com', password='pw12345678', role=UserRole.CANDIDATE)
    emp_x = User.objects.create_user(email='x@example.com', password='pw12345678', role=UserRole.EMPLOYER)
    emp_y = User.objects.create_user(email='y@example.com', password='pw12345678', role=UserRole.EMPLOYER)
    company_x = Company.objects.create(name='X Corp', inn='7700000001')
    company_y = Company.objects.create(name='Y Corp', inn='7700000002')
    CompanyMember.objects.create(user=emp_x, company=company_x)
    CompanyMember.objects.create(user=emp_y, company=company_y)
    yield {
        'a': cand_a, 'b': cand_b, 'emp_x': emp_x, 'emp_y': emp_y,
        'company_x': company_x, 'company_y': company_y,
    }
    _RECENT_EVENTS.clear()


def _offer(company, candidate, status=OfferStatus.SENT, expires_at=None, version=1):
    position = Position.objects.create(
        company=company, title='Dev', specialization='backend', grades=['middle'],
        salary_min=100000, salary_max=200000, salary_type=SalaryType.GROSS,
    )
    return Offer.objects.create(
        company=company, candidate=candidate, position=position,
        title='Secret title', description='d',
        salary_min=150000, salary_max=180000, salary_type=SalaryType.GROSS,
        contact_channel=ContactChannel.TELEGRAM, contact_value='@hr',
        status=status, expires_at=expires_at, version=version,
    )


# --------------------------------------------------------------------------- SSE scoping

@pytest.mark.django_db
class TestEventScoping:

    def test_candidate_does_not_receive_other_candidates_events(self, world, django_capture_on_commit_callbacks):
        a, b = world['a'], world['b']
        qa = register_subscriber(user_id=a.id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                publish_domain_event('offer.created', {
                    'offer_id': '1', 'candidate_id': str(b.id),
                    'company_id': str(world['company_x'].id), 'title': 'B only',
                })
                publish_domain_event('league.updated', {'candidate_id': str(b.id), 'grade': 'senior'})
                publish_domain_event('league.updated', {'candidate_id': str(a.id), 'grade': 'middle'})
            events = _drain(qa)
        finally:
            unregister_subscriber(qa)
        assert [(e['event'], e['data']['candidate_id']) for e in events] == [
            ('league.updated', str(a.id)),
        ]

    def test_employer_receives_only_own_company_offer_events(self, world, django_capture_on_commit_callbacks):
        cx, cy = world['company_x'], world['company_y']
        qx = register_subscriber(user_id=world['emp_x'].id, company_ids=[cx.id])
        try:
            with django_capture_on_commit_callbacks(execute=True):
                publish_domain_event('offer.created', {
                    'offer_id': 'x1', 'candidate_id': str(world['a'].id), 'company_id': str(cx.id),
                })
                publish_domain_event('offer.created', {
                    'offer_id': 'y1', 'candidate_id': str(world['b'].id), 'company_id': str(cy.id),
                })
                publish_domain_event('fsp.synced', {'candidate_id': str(world['a'].id), 'participant_id': 'P1'})
            events = _drain(qx)
        finally:
            unregister_subscriber(qx)
        assert [e['data']['offer_id'] for e in events] == ['x1']

    def test_event_without_audience_goes_to_nobody(self, world, django_capture_on_commit_callbacks):
        qa = register_subscriber(user_id=world['a'].id, company_ids=[world['company_x'].id])
        try:
            with django_capture_on_commit_callbacks(execute=True):
                publish_domain_event('offer.created', {'offer_id': 42})
            assert qa.empty()
        finally:
            unregister_subscriber(qa)

    def test_replay_is_scoped(self, world, django_capture_on_commit_callbacks):
        a, b = world['a'], world['b']
        with django_capture_on_commit_callbacks(execute=True):
            publish_domain_event('league.updated', {'candidate_id': str(b.id), 'grade': 'senior'})
            publish_domain_event('league.updated', {'candidate_id': str(a.id), 'grade': 'middle'})
        qa = register_subscriber(user_id=a.id, replay_recent=True)
        try:
            events = _drain(qa)
        finally:
            unregister_subscriber(qa)
        assert [e['data']['candidate_id'] for e in events] == [str(a.id)]

    def test_rolled_back_event_is_not_delivered(self, world, django_capture_on_commit_callbacks):
        a = world['a']
        qa = register_subscriber(user_id=a.id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                with pytest.raises(RuntimeError):
                    with transaction.atomic():
                        publish_domain_event('league.updated', {'candidate_id': str(a.id)})
                        raise RuntimeError('boom')
            assert qa.empty()
            assert list(_RECENT_EVENTS) == []
        finally:
            unregister_subscriber(qa)

    def test_event_not_delivered_before_commit(self, world, django_capture_on_commit_callbacks):
        a = world['a']
        qa = register_subscriber(user_id=a.id)
        try:
            with django_capture_on_commit_callbacks(execute=False) as callbacks:
                publish_domain_event('league.updated', {'candidate_id': str(a.id)})
                assert qa.empty()
            assert len(callbacks) == 1
        finally:
            unregister_subscriber(qa)


@pytest.mark.django_db
class TestSSEEndpoint:

    def _stream(self, client, url):
        response = client.get(url)
        assert response.status_code == 200
        return b''.join(response.streaming_content).decode('utf-8')

    def test_sse_candidate_stream_is_scoped(self, world, django_capture_on_commit_callbacks):
        a, b = world['a'], world['b']
        with django_capture_on_commit_callbacks(execute=True):
            publish_domain_event('offer.created', {
                'offer_id': 'for-b', 'candidate_id': str(b.id),
                'company_id': str(world['company_x'].id), 'title': 'Leaky title',
            })
            publish_domain_event('league.updated', {'candidate_id': str(a.id), 'grade': 'middle'})
        client = APIClient()
        client.force_authenticate(user=a)
        content = self._stream(client, '/api/events?limit=5')
        assert 'Leaky title' not in content
        assert str(b.id) not in content
        assert 'event: league.updated' in content

    def test_sse_employer_stream_is_scoped(self, world, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            publish_domain_event('offer.created', {
                'offer_id': 'x-offer', 'candidate_id': str(world['a'].id),
                'company_id': str(world['company_x'].id),
            })
            publish_domain_event('offer.created', {
                'offer_id': 'y-offer', 'candidate_id': str(world['b'].id),
                'company_id': str(world['company_y'].id),
            })
        client = APIClient()
        client.force_authenticate(user=world['emp_x'])
        content = self._stream(client, '/api/events?limit=5')
        assert 'x-offer' in content
        assert 'y-offer' not in content

    @pytest.mark.parametrize('bad', ['abc', '-1', '1.5'])
    def test_sse_bad_limit_rejected_before_stream(self, world, bad):
        client = APIClient()
        client.force_authenticate(user=world['a'])
        response = client.get(f'/api/events?limit={bad}')
        assert response.status_code == 422
        assert response['Content-Type'].startswith('application/problem+json')

    def test_sse_requires_auth(self, world):
        response = APIClient().get('/api/events?limit=1')
        # SessionAuthentication has no WWW-Authenticate header, so DRF answers 403.
        assert response.status_code in (401, 403)
        assert not hasattr(response, 'streaming_content')


# --------------------------------------------------------------------------- lazy expiry

@pytest.mark.django_db
class TestLazyExpiry:

    def test_expired_sent_offer_is_persisted_and_raises(self, world):
        offer = _offer(world['company_x'], world['a'], expires_at=timezone.now() - timedelta(hours=1))
        with pytest.raises(OfferExpired) as exc_info:
            OfferService.transition(offer.id, OfferStatus.VIEWED, 1, world['a'].id)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == 'offer_expired'

        offer.refresh_from_db()
        assert offer.status == OfferStatus.EXPIRED
        assert offer.version == 2
        assert OfferEvent.objects.filter(
            offer=offer, from_status=OfferStatus.SENT, to_status=OfferStatus.EXPIRED,
        ).count() == 1
        assert AuditLog.objects.filter(
            action='offer_expired', target_type='Offer', target_id=str(offer.id),
        ).count() == 1

    def test_expiry_survives_outer_atomic_that_catches(self, world):
        offer = _offer(world['company_x'], world['a'], status=OfferStatus.VIEWED,
                       expires_at=timezone.now() - timedelta(hours=1))
        with transaction.atomic():
            try:
                OfferService.transition(offer.id, OfferStatus.ACCEPTED, 1, world['a'].id)
            except OfferExpired:
                pass
        offer.refresh_from_db()
        assert offer.status == OfferStatus.EXPIRED

    def test_expiry_publishes_scoped_event(self, world, django_capture_on_commit_callbacks):
        offer = _offer(world['company_x'], world['a'], expires_at=timezone.now() - timedelta(hours=1))
        qa = register_subscriber(user_id=world['a'].id)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                with pytest.raises(OfferExpired):
                    OfferService.transition(offer.id, OfferStatus.VIEWED, 1, world['a'].id)
            events = _drain(qa)
        finally:
            unregister_subscriber(qa)
        assert [(e['event'], e['data']['status']) for e in events] == [('offer.updated', OfferStatus.EXPIRED)]

    def test_stale_version_checked_before_expiry(self, world):
        offer = _offer(world['company_x'], world['a'], expires_at=timezone.now() - timedelta(hours=1), version=3)
        with pytest.raises(VersionConflict):
            OfferService.transition(offer.id, OfferStatus.VIEWED, 1, world['a'].id)
        offer.refresh_from_db()
        assert offer.status == OfferStatus.SENT

    def test_accepted_offer_past_expiry_can_move_to_interview(self, world):
        offer = _offer(world['company_x'], world['a'], status=OfferStatus.ACCEPTED,
                       expires_at=timezone.now() - timedelta(days=1))
        updated = OfferService.transition(offer.id, OfferStatus.INTERVIEW, 1, world['emp_x'].id)
        assert updated.status == OfferStatus.INTERVIEW
        assert updated.version == 2

    def test_already_expired_offer_still_invalid_transition(self, world):
        offer = _offer(world['company_x'], world['a'], status=OfferStatus.EXPIRED,
                       expires_at=timezone.now() - timedelta(days=1))
        with pytest.raises(InvalidTransition):
            OfferService.transition(offer.id, OfferStatus.VIEWED, 1, world['a'].id)
