from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Seed all initial data (CMS + AMS) in one step"

    def handle(self, *args, **options):
        self.stdout.write("==> Seeding CMS data (companies, templates, users, employees)...")
        call_command("seed_data")

        self.stdout.write("==> Seeding AMS data (users, approval requests, subscriptions)...")
        call_command("ams_seed_data")

        self.stdout.write("==> Seeding AMS test users (role hierarchy)...")
        call_command("seed")

        self.stdout.write(self.style.SUCCESS("\nAll seed data loaded successfully."))
