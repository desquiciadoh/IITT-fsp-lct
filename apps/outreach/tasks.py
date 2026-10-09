"""Celery tasks for outreach application."""
import logging

from celery import shared_task

from outreach.services import OfferService

logger = logging.getLogger(__name__)


@shared_task(name='outreach.tasks.expire_offers')
def expire_offers():
    """Expire offers that have passed their deadline."""
    count = OfferService.expire_offers()
    logger.info("Expired %d stale offers.", count)
    return count
