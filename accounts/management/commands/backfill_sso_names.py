from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backfill first_name/last_name/sso fields for existing SSO users from stored Google profile data"

    def handle(self, *args, **options):
        from allauth.socialaccount.models import SocialAccount

        updated = 0
        for sa in SocialAccount.objects.select_related("user").all():
            user = sa.user
            extra = sa.extra_data or {}
            changed = []

            if not user.first_name and extra.get("given_name"):
                user.first_name = extra["given_name"]
                changed.append("first_name")
            if not user.last_name and extra.get("family_name"):
                user.last_name = extra["family_name"]
                changed.append("last_name")
            if not user.sso_provider:
                user.sso_provider = sa.provider
                user.sso_subject = sa.uid
                changed += ["sso_provider", "sso_subject"]

            if changed:
                user.save(update_fields=changed)
                updated += 1
                self.stdout.write(f"  Updated {user.email}: {', '.join(changed)}")

        if updated:
            self.stdout.write(self.style.SUCCESS(f"Done — {updated} user(s) updated."))
        else:
            self.stdout.write("Done — all SSO users already have name data, nothing to update.")
