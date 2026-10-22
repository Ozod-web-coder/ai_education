from django.core.management.base import BaseCommand

from apps.booking.services import release_expired_holds


class Command(BaseCommand):
    help = "Снять истёкшие брони мест"

    def handle(self, *args, **options):
        count = release_expired_holds()
        self.stdout.write(self.style.SUCCESS(f"Снято броней: {count}"))
