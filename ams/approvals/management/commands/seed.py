"""
Management command: python manage.py seed

Creates a complete set of test users covering every role, with proper
reports_to hierarchy for AMS approval flow.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

PASSWORD = 'Pass@1234'

# Roles: admin, finance_head, finance_executive, manager, employee, viewer, it
USERS = [
    # ── C-suite / top-level (no reports_to) ──────────────────────────────────
    {
        'email': 'admin@bv.com',
        'username': 'admin_bv',
        'first_name': 'Arjun',
        'last_name': 'Admin',
        'role': 'admin',
        'reports_to_email': None,
    },
    {
        'email': 'finance.head@bv.com',
        'username': 'finance_head_bv',
        'first_name': 'Fatima',
        'last_name': 'Finance Head',
        'role': 'finance_head',
        'reports_to_email': None,
    },
    {
        'email': 'carol@bv.com',
        'username': 'carol',
        'first_name': 'Carol',
        'last_name': 'Finance',
        'role': 'finance_executive',
        'reports_to_email': None,
    },
    {
        'email': 'eve@bv.com',
        'username': 'eve',
        'first_name': 'Eve',
        'last_name': 'Finance',
        'role': 'finance_executive',
        'reports_to_email': None,
    },
    {
        'email': 'dave@bv.com',
        'username': 'dave',
        'first_name': 'Dave',
        'last_name': 'IT',
        'role': 'it',
        'reports_to_email': None,
    },
    {
        'email': 'victor@bv.com',
        'username': 'victor',
        'first_name': 'Victor',
        'last_name': 'Viewer',
        'role': 'viewer',
        'reports_to_email': None,
    },
    # ── Managers (report to admin) ────────────────────────────────────────────
    {
        'email': 'bob@bv.com',
        'username': 'bob',
        'first_name': 'Bob',
        'last_name': 'Manager',
        'role': 'manager',
        'reports_to_email': 'admin@bv.com',
    },
    {
        'email': 'meera@bv.com',
        'username': 'meera',
        'first_name': 'Meera',
        'last_name': 'Manager',
        'role': 'manager',
        'reports_to_email': 'admin@bv.com',
    },
    # ── Employees (report to managers) ───────────────────────────────────────
    {
        'email': 'alice@bv.com',
        'username': 'alice',
        'first_name': 'Alice',
        'last_name': 'Employee',
        'role': 'employee',
        'reports_to_email': 'bob@bv.com',
    },
    {
        'email': 'raj@bv.com',
        'username': 'raj',
        'first_name': 'Raj',
        'last_name': 'Employee',
        'role': 'employee',
        'reports_to_email': 'bob@bv.com',
    },
    {
        'email': 'priya@bv.com',
        'username': 'priya_emp',
        'first_name': 'Priya',
        'last_name': 'Employee',
        'role': 'employee',
        'reports_to_email': 'meera@bv.com',
    },
    {
        'email': 'sam@bv.com',
        'username': 'sam',
        'first_name': 'Sam',
        'last_name': 'Employee',
        'role': 'employee',
        'reports_to_email': 'meera@bv.com',
    },
]


class Command(BaseCommand):
    help = 'Seed AMS test users covering every role with proper hierarchy'

    def handle(self, *args, **options):
        from accounts.models import User

        with transaction.atomic():
            created_users = {}

            # First pass: create/update users (without reports_to)
            for data in USERS:
                user, created = User.objects.get_or_create(
                    email=data['email'],
                    defaults={
                        'username': data['username'],
                        'first_name': data['first_name'],
                        'last_name': data['last_name'],
                        'role': data['role'],
                    },
                )
                if created:
                    user.set_password(PASSWORD)
                    user.save()
                    self.stdout.write(f'  Created : {user.email} ({data["role"]})')
                else:
                    # Update role in case it changed
                    user.role = data['role']
                    user.set_password(PASSWORD)
                    user.save(update_fields=['role', 'password'])
                    self.stdout.write(f'  Updated : {user.email} ({data["role"]})')
                created_users[data['email']] = (user, data['reports_to_email'])

            # Second pass: wire up reports_to hierarchy
            for email, (user, reports_to_email) in created_users.items():
                if reports_to_email and reports_to_email in created_users:
                    manager = created_users[reports_to_email][0]
                    if user.reports_to_id != manager.pk:
                        user.reports_to = manager
                        user.save(update_fields=['reports_to'])
                elif not reports_to_email and user.reports_to_id is not None:
                    user.reports_to = None
                    user.save(update_fields=['reports_to'])

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✓ Seed complete. All passwords: ' + PASSWORD))
        self.stdout.write('')
        self.stdout.write('  Role            Email                   Login use-case')
        self.stdout.write('  ─────────────── ─────────────────────── ──────────────────────────────')
        self.stdout.write('  Admin           admin@bv.com            Full access, no approval chain')
        self.stdout.write('  Finance Head    finance.head@bv.com     Finance queue + CMS documents')
        self.stdout.write('  Finance Exec    carol@bv.com            Approves pending_finance requests')
        self.stdout.write('  Finance Exec    eve@bv.com              Approves pending_finance requests')
        self.stdout.write('  IT              dave@bv.com             Provisions subscriptions')
        self.stdout.write('  Viewer          victor@bv.com           Read-only audit access')
        self.stdout.write('  Manager         bob@bv.com              Approves team requests')
        self.stdout.write('  Manager         meera@bv.com            Approves team requests')
        self.stdout.write('  Employee        alice@bv.com            Submits → bob → finance')
        self.stdout.write('  Employee        raj@bv.com              Submits → bob → finance')
        self.stdout.write('  Employee        priya@bv.com            Submits → meera → finance')
        self.stdout.write('  Employee        sam@bv.com              Submits → meera → finance')
