"""
Management command: python manage.py run_cron

Checks:
1. Subscriptions expiring in exactly 10, 5, or 1 day(s) → send staged renewal reminders
2. Subscriptions in 'renewing' state past their expires_on → move to active_pending_renewal
3. Subscriptions in 'active_pending_renewal' past 30 days → escalate to finance
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

REMINDER_SCHEDULE = [
    (10, 'renewal_reminder_10d', 'Renewal reminder'),
    (5,  'renewal_reminder_5d',  'Renewal reminder'),
    (1,  'renewal_reminder_1d',  'Final renewal reminder — expires tomorrow'),
]


class Command(BaseCommand):
    help = 'Run scheduled cron tasks: renewal reminders, expiry checks, escalations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        self.stdout.write(self.style.NOTICE(f'[run_cron] Starting cron run for {today}'))

        self._check_renewal_reminders(today, dry_run)
        self._check_expired_subscriptions(today, dry_run)
        self._check_expired_renewing(today, dry_run)
        self._check_escalations(today, dry_run)

        self.stdout.write(self.style.SUCCESS('[run_cron] Done.'))

    def _check_renewal_reminders(self, today, dry_run):
        """Send renewal reminders at 10, 5, and 1 day(s) before expiry."""
        from ams.approvals.models import ApprovalRequest
        from ams.notifications.services import send_notification

        for days_left, action_type, label in REMINDER_SCHEDULE:
            target_date = today + timedelta(days=days_left)
            due = ApprovalRequest.objects.filter(
                request_type='subscription',
                state='active',
                expires_on=target_date,
            ).select_related('submitted_by')

            self.stdout.write(
                f'[run_cron] {label} ({days_left}d): {due.count()} subscription(s) expiring on {target_date}'
            )

            for req in due:
                self.stdout.write(f'  >> {req.service_name} (id={req.id}) expires in {days_left} day(s)')

                if days_left == 1:
                    subject = f'Final reminder: {req.service_name} expires tomorrow'
                    body = (
                        f'Your subscription to {req.service_name} expires TOMORROW ({req.expires_on}).\n\n'
                        f'Please visit the AMS portal immediately to initiate renewal.'
                    )
                else:
                    subject = f'Renewal reminder: {req.service_name} expires in {days_left} days'
                    body = (
                        f'Your subscription to {req.service_name} expires on {req.expires_on} '
                        f'({days_left} days from now).\n\n'
                        f'Please visit the AMS portal to initiate renewal.'
                    )

                if not dry_run:
                    sent = send_notification(
                        subject_id=req.id,
                        action_type=action_type,
                        target_date=req.expires_on,
                        recipient=req.submitted_by,
                        subject=subject,
                        body=body,
                    )
                    if sent:
                        self.stdout.write(self.style.SUCCESS(f'    Reminder sent to {req.submitted_by.email}'))
                    else:
                        self.stdout.write(f'    Reminder already sent (idempotent)')

    def _check_expired_subscriptions(self, today, dry_run):
        """
        Active subscriptions whose expires_on is in the past
        → transition to 'expired' and notify the subscriber.
        """
        from ams.approvals.models import ApprovalRequest
        from ams.notifications.services import send_notification

        overdue = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='active',
            expires_on__lt=today,
        ).select_related('submitted_by')

        self.stdout.write(f'[run_cron] Expired subscriptions: {overdue.count()} to mark as expired')

        for req in overdue:
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) expired on {req.expires_on}')
            if not dry_run:
                req.expire()
                req.save()
                send_notification(
                    subject_id=req.id,
                    action_type='subscription_expired',
                    target_date=req.expires_on,
                    recipient=req.submitted_by,
                    subject=f'Subscription expired: {req.service_name}',
                    body=(
                        f'Your subscription to {req.service_name} expired on {req.expires_on}.\n\n'
                        f'Please visit the AMS portal to submit a new subscription request if needed.'
                    ),
                )
                self.stdout.write(self.style.WARNING(f'    Marked expired, notified {req.submitted_by.email}'))

    def _check_expired_renewing(self, today, dry_run):
        """
        Subscriptions in 'renewing' state where expires_on < today
        → transition back to active_pending_renewal (renewal in progress, extend notice).
        """
        from ams.approvals.models import ApprovalRequest

        expired_renewing = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='renewing',
            expires_on__lt=today,
        )

        self.stdout.write(f'[run_cron] Expired-while-renewing: {expired_renewing.count()} subscriptions')

        for req in expired_renewing:
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) expired on {req.expires_on} while renewing')
            if not dry_run:
                # Already in renewing, just log a reminder
                from ams.notifications.services import send_notification
                from accounts.models import User
                finance = User.objects.filter(role=User.ROLE_FINANCE_EXECUTIVE, is_active=True).first()
                if finance:
                    send_notification(
                        subject_id=req.id,
                        action_type='renewal_overdue_finance',
                        target_date=today,
                        recipient=finance,
                        subject=f'Renewal overdue: {req.service_name}',
                        body=(
                            f'Subscription {req.service_name} (id={req.id}) for '
                            f'{req.submitted_by.display_name} has passed its expiry date '
                            f'({req.expires_on}) and is still awaiting renewal approval.'
                        ),
                    )

    def _check_escalations(self, today, dry_run):
        """
        Subscriptions in active_pending_renewal where expires_on < today - 30
        → escalate to finance.
        """
        from ams.approvals.models import ApprovalRequest
        from ams.notifications.services import send_notification
        from accounts.models import User

        cutoff = today - timedelta(days=30)
        overdue = ApprovalRequest.objects.filter(
            request_type='subscription',
            state='active_pending_renewal',
            expires_on__lt=cutoff,
        ).select_related('submitted_by')

        self.stdout.write(f'[run_cron] Escalations: {overdue.count()} subscriptions overdue by 30+ days')

        finance = User.objects.filter(role=User.ROLE_FINANCE_EXECUTIVE, is_active=True).first()

        for req in overdue:
            days_overdue = (today - req.expires_on).days
            self.stdout.write(f'  >> {req.service_name} (id={req.id}) overdue by {days_overdue} days')

            if not dry_run and finance:
                send_notification(
                    subject_id=req.id,
                    action_type='renewal_escalation_30d',
                    target_date=today,
                    recipient=finance,
                    subject=f'ESCALATION: {req.service_name} overdue renewal ({days_overdue} days)',
                    body=(
                        f'Subscription {req.service_name} for {req.submitted_by.display_name} '
                        f'expired on {req.expires_on} ({days_overdue} days ago) '
                        f'and is still in active_pending_renewal state.\n\n'
                        f'Please take action immediately.'
                    ),
                )
                self.stdout.write(self.style.WARNING(f'    Escalation sent to {finance.email}'))
