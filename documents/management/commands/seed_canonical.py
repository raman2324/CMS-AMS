"""
seed_canonical — single source of truth for all demo seed data (CMS + AMS).

Supersedes the three legacy commands (seed_data, ams_seed_data, seed).
Called exclusively via seed_all. Safe to re-run — all writes use get_or_create.

Usage:
    python manage.py seed_canonical
    python manage.py seed_canonical --force   # Re-seed templates even if they exist
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from documents.models import Company, Document, Employee, LetterTemplate, TEMPLATE_EXTRA_SCHEMAS

User = get_user_model()

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

_PASS_ADMIN    = 'Adm!n@99'
_PASS_FIN_HEAD = 'F!nHead8'
_PASS_DEFAULT  = 'pass1234'

# ---------------------------------------------------------------------------
# Canonical users
# ---------------------------------------------------------------------------

USERS = [
    # Admin — template management, manage panel (no CMS doc permissions by default)
    {
        'email':          'admin@bv.com',
        'username':       'admin_bv',
        'first_name':     'Arjun',
        'last_name':      'Admin',
        'role':           'admin',
        'is_staff':       True,
        'is_superuser':   True,
        'password':       _PASS_ADMIN,
        'reports_to_email': None,
    },
    # Finance Head — full CMS (void/lock/all docs), AMS view-all, user & company mgmt
    {
        'email':          'finance.head@bv.com',
        'username':       'finance_head_bv',
        'first_name':     'Fatima',
        'last_name':      'Head',
        'role':           'finance_head',
        'password':       _PASS_FIN_HEAD,
        'reports_to_email': None,
    },
    # Finance Executive — generate letters, AMS finance queue approver
    {
        'email':          'fin.exec@bv.com',
        'username':       'example_fin_exec',
        'first_name':     'Carol',
        'last_name':      'Finance',
        'role':           'finance_executive',
        'password':       _PASS_DEFAULT,
        'reports_to_email': None,
    },
    # Manager — approves team AMS requests (C-suite: own requests skip manager step)
    {
        'email':          'manager@bv.com',
        'username':       'example_manager',
        'first_name':     'Bob',
        'last_name':      'Manager',
        'role':           'manager',
        'password':       _PASS_DEFAULT,
        'reports_to_email': None,
    },
    # Employee — submits AMS requests, routed via example_manager
    {
        'email':          'employee@bv.com',
        'username':       'example_employee',
        'first_name':     'Alice',
        'last_name':      'Employee',
        'role':           'employee',
        'password':       _PASS_DEFAULT,
        'reports_to_email': 'manager@bv.com',
    },
    # Viewer — read-only access to document list and audit
    {
        'email':          'viewer@bv.com',
        'username':       'example_viewer',
        'first_name':     'Viewer',
        'last_name':      'User',
        'role':           'viewer',
        'password':       _PASS_DEFAULT,
        'reports_to_email': None,
    },
]

# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

COMPANIES = [
    {
        "name": "Cadient Talent",
        "short_name": "cadient",
        "registered_address": "Level 5, Prestige Tower,\nMG Road, Bengaluru — 560001,\nKarnataka, India",
        "cin": "U72900KA2005PTC036789",
        "gstin": "29AABCC1234F1Z5",
        "signatory_name": "Rajesh Kumar",
        "signatory_designation": "Director, Human Resources",
    },
    {
        "name": "Vorro",
        "short_name": "vorro",
        "registered_address": "Unit 12, Cyber Pearl,\nHiTech City, Hyderabad — 500081,\nTelangana, India",
        "cin": "U74999TG2010PTC068432",
        "gstin": "36AABCV5678G1Z3",
        "signatory_name": "Priya Sharma",
        "signatory_designation": "Vice President, People Operations",
    },
    {
        "name": "CommerceV3",
        "short_name": "cv3",
        "registered_address": "402, Kalpataru Synergy,\nVakola, Santacruz (East),\nMumbai — 400055, Maharashtra, India",
        "cin": "U72200MH2008PTC181234",
        "gstin": "27AABCC9012H1Z7",
        "signatory_name": "Anita Mehta",
        "signatory_designation": "Head of HR & Administration",
    },
    {
        "name": "Basis Vectors Portfolio Services India Private Limited",
        "short_name": "bv",
        "registered_address": "Plot No. 14, Sector 44,\nGurugram — 122003,\nHaryana, India",
        "cin": "U74999HR2020PTC091234",
        "gstin": "06AABCB1234K1Z8",
        "signatory_name": "Authorized Signatory",
        "signatory_designation": "Director",
    },
]

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATE_NAMES = [
    ("offer_letter",            "Offer Letter"),
    ("salary_letter",           "Salary Letter"),
    ("noc",                     "No Objection Certificate"),
    ("experience_certificate",  "Experience Certificate"),
]

# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

SAMPLE_EMPLOYEES = [
    {
        "short_name": "cadient",
        "name": "Raman Sharma",
        "email": "raman.sharma@cadienttalent.com",
        "employee_code": "CT001",
        "designation": "Senior Software Engineer",
        "role": "Backend Engineer",
        "department": "Engineering",
        "joining_date": "2022-03-15",
        "salary_current": 120000,
    },
    {
        "short_name": "cadient",
        "name": "Priya Nair",
        "email": "priya.nair@cadienttalent.com",
        "employee_code": "CT002",
        "designation": "Product Manager",
        "role": "Product",
        "department": "Product",
        "joining_date": "2021-07-01",
        "salary_current": 150000,
    },
    {
        "short_name": "vorro",
        "name": "Arun Mehta",
        "email": "arun.mehta@vorro.com",
        "employee_code": "VR001",
        "designation": "HR Business Partner",
        "role": "HR",
        "department": "Human Resources",
        "joining_date": "2023-01-10",
        "salary_current": 95000,
    },
    {
        "short_name": "vorro",
        "name": "Sunita Rao",
        "email": "sunita.rao@vorro.com",
        "employee_code": "VR002",
        "designation": "Finance Analyst",
        "role": "Finance",
        "department": "Finance",
        "joining_date": "2020-09-01",
        "salary_current": 85000,
    },
    {
        "short_name": "cv3",
        "name": "Raman Kumar",
        "email": "raman.kumar@commercev3.com",
        "employee_code": "CV3001",
        "designation": "Full Stack Developer",
        "role": "Developer",
        "department": "Engineering",
        "joining_date": "2023-06-01",
        "salary_current": 110000,
    },
    {
        "short_name": "cv3",
        "name": "Deepa Pillai",
        "email": "deepa.pillai@commercev3.com",
        "employee_code": "CV3002",
        "designation": "HR Manager",
        "role": "HR",
        "department": "Human Resources",
        "joining_date": "2019-04-15",
        "salary_current": 130000,
    },
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Seed all canonical demo data: users, companies, templates, employees, AMS requests, documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-seed templates even if they already exist.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        admin_user = self._seed_users()
        self._seed_companies()
        self._seed_templates(admin_user, force=force)
        self._seed_employees()
        self._seed_documents()

        self.stdout.write(self.style.SUCCESS("\n✓ Seed complete.\n"))
        self.stdout.write("  Role              Email                    Password")
        self.stdout.write("  ─────────────── ──────────────────────── ─────────────")
        self.stdout.write(f"  Admin           admin@bv.com             {_PASS_ADMIN}")
        self.stdout.write(f"  Finance Head    finance.head@bv.com      {_PASS_FIN_HEAD}")
        self.stdout.write(f"  Finance Exec    fin.exec@bv.com          {_PASS_DEFAULT}")
        self.stdout.write(f"  Manager         manager@bv.com           {_PASS_DEFAULT}")
        self.stdout.write(f"  Employee        employee@bv.com          {_PASS_DEFAULT}")
        self.stdout.write(f"  Viewer          viewer@bv.com            {_PASS_DEFAULT}")

    # ------------------------------------------------------------------

    def _seed_users(self):
        self.stdout.write("Seeding canonical users…")
        created_users = {}

        # First pass: create users without reports_to (avoids FK ordering issues)
        for data in USERS:
            user, created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'username':     data['username'],
                    'first_name':   data['first_name'],
                    'last_name':    data['last_name'],
                    'role':         data['role'],
                    'is_staff':     data.get('is_staff', False),
                    'is_superuser': data.get('is_superuser', False),
                },
            )
            if created:
                user.set_password(data['password'])
                user.save()
                self.stdout.write(f"  Created : {user.email} ({data['role']})")
            else:
                self.stdout.write(f"  Exists  : {user.email} ({user.role})")
            created_users[data['email']] = (user, data['reports_to_email'])

        # Second pass: wire reports_to hierarchy
        for email, (user, reports_to_email) in created_users.items():
            if reports_to_email and reports_to_email in created_users:
                manager_user = created_users[reports_to_email][0]
                if user.reports_to_id != manager_user.pk:
                    user.reports_to = manager_user
                    user.save(update_fields=['reports_to'])

        # admin_bv is always first in USERS and always exists after this pass
        return created_users['admin@bv.com'][0]

    def _seed_companies(self):
        self.stdout.write("Seeding companies…")
        for data in COMPANIES:
            company, created = Company.objects.get_or_create(
                short_name=data["short_name"],
                defaults=data,
            )
            verb = "Created" if created else "Exists "
            self.stdout.write(f"  {verb}: {company.name}")

    def _seed_templates(self, created_by, force=False):
        self.stdout.write("Seeding letter templates…")
        for slug, name in TEMPLATE_NAMES:
            template_file = f"letter_templates/{slug}.html"
            try:
                html_content = get_template(template_file).template.source
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Warning : could not load {template_file}: {exc}"))
                html_content = f"<p>Template content for {name}. Edit via admin.</p>"

            active = LetterTemplate.objects.filter(name=name, is_active=True).first()
            if active and not force:
                self.stdout.write(f"  Exists  : {name} (skipped — use --force to re-seed)")
                continue

            if active and force:
                active.html_content = html_content
                active.extra_variables_schema = TEMPLATE_EXTRA_SCHEMAS.get(slug, {})
                active.save(update_fields=["html_content", "extra_variables_schema"])
                self.stdout.write(f"  Updated : {active}")
            else:
                tmpl = LetterTemplate(
                    name=name,
                    html_content=html_content,
                    extra_variables_schema=TEMPLATE_EXTRA_SCHEMAS.get(slug, {}),
                    created_by=created_by,
                )
                tmpl.save()
                tmpl.activate()
                self.stdout.write(f"  Created : {tmpl}")

    def _seed_employees(self):
        self.stdout.write("Seeding sample employees…")
        for data in SAMPLE_EMPLOYEES:
            short_name = data.pop("short_name")
            try:
                company = Company.objects.get(short_name=short_name)
            except Company.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  Skipped : company '{short_name}' not found"))
                data["short_name"] = short_name
                continue
            joining_date = date.fromisoformat(data.pop("joining_date"))
            employee, created = Employee.objects.get_or_create(
                employee_code=data["employee_code"],
                defaults={**data, "company": company, "joining_date": joining_date},
            )
            verb = "Created" if created else "Exists "
            self.stdout.write(f"  {verb}: {employee.name} ({employee.employee_code})")
            # Restore mutated keys for idempotent re-runs
            data["short_name"] = short_name
            data["joining_date"] = str(joining_date)

    def _seed_documents(self):
        self.stdout.write("Seeding demo documents…")
        from documents.services import generate_document

        issuer = User.objects.filter(email='finance.head@bv.com').first()
        if not issuer:
            self.stdout.write(self.style.WARNING("  Skipped : finance_head_bv user not found"))
            return

        # (employee_code, template_name, variables)
        seeds = [
            ("CT001", "Offer Letter", {
                "subject":          "Offer of Employment — Senior Software Engineer",
                "ctc_annual":       "14,40,000",
                "byod_allowance":   "24,000",
                "variable_pay":     "1,44,000",
                "offer_expiry_date": "2024-06-01",
            }),
            ("CT002", "Salary Letter", {
                "salary_monthly":  "125000",
                "salary_annual":   "1500000",
                "effective_date":  "2024-03-01",
            }),
            ("VR001", "Experience Certificate", {
                "last_working_date": "2024-03-31",
            }),
            ("VR002", "No Objection Certificate", {
                "purpose":     "Bank loan application",
                "valid_until": "2024-12-31",
            }),
            ("CV3001", "Offer Letter", {
                "subject":           "Offer of Employment — Full Stack Developer",
                "ctc_annual":        "13,20,000",
                "byod_allowance":    "24,000",
                "variable_pay":      "1,32,000",
                "offer_expiry_date": "2024-07-01",
            }),
        ]

        for emp_code, tmpl_name, variables in seeds:
            employee = Employee.objects.filter(employee_code=emp_code).first()
            template = LetterTemplate.objects.filter(name=tmpl_name, is_active=True).first()
            if not employee or not template:
                self.stdout.write(self.style.WARNING(f"  Skipped : {emp_code}/{tmpl_name} — not found"))
                continue
            if Document.objects.filter(recipient=employee, template=template).exists():
                self.stdout.write(f"  Exists  : {tmpl_name} for {emp_code}")
                continue
            try:
                document, _ = generate_document(template.id, employee.id, variables, issuer)
                self.stdout.write(f"  Created : {tmpl_name} for {emp_code} → {document.id}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Failed  : {tmpl_name} for {emp_code}: {exc}"))
