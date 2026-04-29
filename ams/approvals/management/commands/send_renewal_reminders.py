from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from ams.approvals.models import ApprovalRequest
from ams.notifications.services import send_notification


class Command(BaseCommand):
    help = 'Send renewal reminder emails for subscriptions expiring within 10 days (runs daily)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which reminders would be sent without actually sending them',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()
        reminder_date = today + timedelta(days=10)

        if dry_run:
            self.stdout.write(self.style.WARNING('[dry-run] No emails will be sent.'))

        expiring_soon = ApprovalRequest.objects.filter(
            state='active',
            request_type='subscription',
            billing_period__in=['monthly', 'annual'],
            expires_on__lte=reminder_date,
            expires_on__gte=today,
        ).select_related('submitted_by')

        self.stdout.write(
            f'[send_renewal_reminders] {expiring_soon.count()} subscription(s) expiring within 10 days'
        )

        count = 0
        for req in expiring_soon:
            days_left = (req.expires_on - today).days
            renewal_link = f"{settings.SITE_URL}/ams/requests/{req.id}/"

            self.stdout.write(
                f'  >> {req.service_name} (id={req.id}) — '
                f'expires {req.expires_on} ({days_left} day(s) left) — '
                f'owner: {req.submitted_by.email}'
            )

            if dry_run:
                continue

            sent = send_notification(
                subject_id=req.id,
                action_type='renewal_reminder_10day',
                target_date=req.expires_on,
                recipient=req.submitted_by,
                subject=(
                    f'Action Required: "{req.service_name}" expires in {days_left} day(s) — Renew now'
                ),
                body=(
                    f'Hi {req.submitted_by.display_name},\n\n'
                    f'Your subscription to {req.service_name} is expiring soon '
                    f'and the renewal window is now open.\n\n'
                    f'  Expiry date : {req.expires_on}\n'
                    f'  Days left   : {days_left}\n'
                    f'  Cost        : ${req.cost} / {req.get_billing_period_display()}\n\n'
                    f'Please log in to the AMS portal and click "Renew Subscription" '
                    f'to avoid any service interruption:\n'
                    f'  {renewal_link}\n\n'
                    f'If you have already initiated a renewal, you can ignore this email.\n\n'
                    f'— AMS Notifications'
                ),
            )

            if sent:
                count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'     Reminder sent to {req.submitted_by.email}')
                )
            else:
                self.stdout.write(f'     Already sent for this expiry cycle (skipped)')

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f'[send_renewal_reminders] Done. Sent {count} reminder(s).'))
