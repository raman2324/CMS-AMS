"""
Management command: seed_data

Creates initial companies, letter templates, and demo users.
Safe to re-run — uses get_or_create for idempotency.

Usage:
    python manage.py seed_data
    python manage.py seed_data --force   # Re-create templates even if they exist
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.template.loader import get_template

from documents.models import Company, Document, Employee, LetterTemplate, TEMPLATE_EXTRA_SCHEMAS

User = get_user_model()


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

# (file_slug, display_name) — file_slug maps to letter_templates/{slug}.html
TEMPLATE_NAMES = [
    ("offer_letter",          "Offer Letter"),
    ("salary_letter",         "Salary Letter"),
    ("noc",                   "No Objection Certificate"),
    ("experience_certificate","Experience Certificate"),
]

SAMPLE_EMPLOYEES = [
    # Cadient Talent
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
    # Vorro
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
    # CommerceV3
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


class Command(BaseCommand):
    help = "Seed initial companies, letter templates, and demo users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-seed templates even if they already exist.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        self._seed_companies()
        admin_user = self._seed_users()
        self._seed_templates(admin_user, force=force)
        self._seed_employees()
        self._seed_documents()

        self.stdout.write(self.style.SUCCESS("\n✓ Seed complete. See README.md for default credentials."))

    # ------------------------------------------------------------------

    def _seed_companies(self):
        self.stdout.write("Seeding companies…")
        for data in COMPANIES:
            company, created = Company.objects.get_or_create(
                short_name=data["short_name"],
                defaults=data,
            )
            verb = "Created" if created else "Exists "
            self.stdout.write(f"  {verb}: {company.name}")

    def _seed_users(self):
        self.stdout.write("Seeding demo users…")
        users = [
            dict(username="admin", email="admin@example.com", first_name="Admin",
                 last_name="User", role="admin", password="Admin@1234", is_staff=True, is_superuser=True),
            dict(username="finance_head", email="finhead@example.com", first_name="Finance",
                 last_name="Head", role="finance_head", password="Finance@1234", is_staff=True),
            dict(username="issuer", email="issuer@example.com", first_name="Issuer",
                 last_name="Demo", role="finance_executive", password="Issuer@1234"),
            dict(username="issuer2", email="issuer2@example.com", first_name="Priya",
                 last_name="Issuer", role="finance_executive", password="Issuer2@1234"),
            dict(username="issuer3", email="issuer3@example.com", first_name="Arun",
                 last_name="Issuer", role="finance_executive", password="Issuer3@1234"),
            dict(username="viewer", email="viewer@example.com", first_name="Viewer",
                 last_name="Demo", role="viewer", password="Viewer@1234"),
        ]
        admin_user = None
        for u in users:
            password = u.pop("password")
            user, created = User.objects.get_or_create(
                username=u["username"],
                defaults=u,
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"  Created : {user.username} / {password}")
            else:
                self.stdout.write(f"  Exists  : {user.username}")
            if u.get("username") == "admin" or user.username == "admin":
                admin_user = user
        return admin_user or User.objects.filter(role="admin").first() or User.objects.first()

    def _seed_employees(self):
        self.stdout.write("Seeding sample employees…")
        from datetime import date
        for data in SAMPLE_EMPLOYEES:
            short_name = data.pop("short_name")
            try:
                company = Company.objects.get(short_name=short_name)
            except Company.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  Skipped: company {short_name} not found"))
                data["short_name"] = short_name
                continue
            joining_date = date.fromisoformat(data.pop("joining_date"))
            employee, created = Employee.objects.get_or_create(
                employee_code=data["employee_code"],
                defaults={**data, "company": company, "joining_date": joining_date},
            )
            verb = "Created" if created else "Exists "
            self.stdout.write(f"  {verb}: {employee.name} ({employee.employee_code})")
            # Restore for idempotency if re-run
            data["short_name"] = short_name
            data["joining_date"] = str(joining_date)

    def _seed_documents(self):
        self.stdout.write("Seeding demo documents…")
        from documents.services import generate_document

        issuer = User.objects.filter(username="issuer").first()
        if not issuer:
            self.stdout.write(self.style.WARNING("  Skipped: issuer user not found"))
            return

        # 5 document seeds: (employee_code, template_name, extra_variables)
        seeds = [
            ("CT001", "Offer Letter",             {"position": "Senior Software Engineer", "start_date": "May 1, 2024", "ctc": "14,40,000"}),
            ("CT002", "Salary Letter",            {"month": "March 2024", "net_salary": "1,25,000"}),
            ("VR001", "Experience Certificate",   {"last_working_day": "March 31, 2024"}),
            ("VR002", "No Objection Certificate", {"purpose": "Bank loan application", "valid_until": "December 31, 2024"}),
            ("CV3001", "Offer Letter",            {"position": "Full Stack Developer", "start_date": "June 1, 2023", "ctc": "13,20,000"}),
        ]

        for emp_code, tmpl_name, variables in seeds:
            # Idempotent: skip if a generated document already exists for this employee+template
            employee = Employee.objects.filter(employee_code=emp_code).first()
            template = LetterTemplate.objects.filter(name=tmpl_name, is_active=True).first()
            if not employee or not template:
                self.stdout.write(self.style.WARNING(f"  Skipped: {emp_code}/{tmpl_name} — not found"))
                continue
            if Document.objects.filter(recipient=employee, template=template).exists():
                self.stdout.write(f"  Exists  : {tmpl_name} for {emp_code}")
                continue
            try:
                document, _ = generate_document(template.id, employee.id, variables, issuer)
                self.stdout.write(f"  Created : {tmpl_name} for {emp_code} → {document.id}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Failed  : {tmpl_name} for {emp_code}: {exc}"))

    def _seed_templates(self, created_by, force=False):
        self.stdout.write("Seeding letter templates…")
        for slug, name in TEMPLATE_NAMES:
            # Load raw HTML source — keep {{ variable }} placeholders intact.
            template_file = f"letter_templates/{slug}.html"
            try:
                html_content = get_template(template_file).template.source
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"  Warning: could not load {template_file}: {exc}"))
                html_content = f"<p>Template content for {name}. Edit via admin.</p>"

            active = LetterTemplate.objects.filter(name=name, is_active=True).first()
            if active and not force:
                self.stdout.write(f"  Exists  : {name} (skipped — use --force to re-seed)")
                continue

            if active and force:
                # Update the active version in-place rather than inserting a duplicate.
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
                tmpl.save()   # version auto-incremented via _state.adding
                tmpl.activate()
                self.stdout.write(f"  Created : {tmpl}")
