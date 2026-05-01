from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Seed all initial data (CMS + AMS) in one step"

    def handle(self, *args, **options):
        self.stdout.write("==> Seeding all initial data (CMS + AMS)...")
        call_command("seed_canonical")

        self.stdout.write(self.style.SUCCESS("\nAll seed data loaded successfully."))
