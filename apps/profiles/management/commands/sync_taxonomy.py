"""Management command to sync taxonomy skills from content/skills.yaml into Skill model rows."""

from django.core.management.base import BaseCommand
from django.db import transaction
from taxonomy.loader import load_skills

from profiles.models import Skill


def sync_taxonomy_to_db() -> int:
    """Synchronize skills from content/skills.yaml into the database."""
    catalog = load_skills(force_reload=True)
    with transaction.atomic():
        count = 0
        for entry in catalog.values():
            Skill.objects.update_or_create(
                id=entry.id,
                defaults={
                    "name": entry.name,
                    "topic": entry.topic,
                    "aliases": entry.aliases,
                    "related": entry.related,
                },
            )
            count += 1
    return count


class Command(BaseCommand):
    help = "Sync canonical skills from content/skills.yaml into Skill model rows"

    def handle(self, *args, **options):
        count = sync_taxonomy_to_db()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced {count} skills."))
