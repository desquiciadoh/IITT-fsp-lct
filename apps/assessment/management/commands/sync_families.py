"""Management command to sync question family metadata into ItemFamily model rows."""

from django.core.management.base import BaseCommand

from assessment.engine_adapter import sync_families_to_db


class Command(BaseCommand):
    help = "Sync active question family metadata into ItemFamily model rows"

    def handle(self, *args, **options):
        count = sync_families_to_db()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced {count} item families."))
