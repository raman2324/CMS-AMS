"""
Management command: generate_bulk

Generate letters in bulk from a CSV file. Designed for annual increment day
and similar high-volume scenarios (200+ letters at once).

Usage:
    python manage.py generate_bulk \\
        --template salary_letter \\
        --csv /path/to/employees.csv \\
        --actor admin \\
        --output-dir /tmp/salary_letters/ \\
        [--dry-run]

CSV columns (all required unless noted):
    employee_code, issue_date, effective_date, salary_monthly, salary_annual
    [optional: basic, hra, ref_number]

Any column matching a template variable is passed through automatically.
"""
import csv
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from documents.models import LetterTemplate, Employee
from documents.services import generate_document

User = get_user_model()


class Command(BaseCommand):
    help = "Bulk-generate letters from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("--template", required=True,
                            help="Template name slug, e.g. salary_letter")
        parser.add_argument("--csv", required=True, dest="csv_path",
                            help="Path to input CSV file")
        parser.add_argument("--actor", default="admin",
                            help="Username of the user generating the documents (default: admin)")
        parser.add_argument("--output-dir", dest="output_dir", default=".",
                            help="Directory to save generated PDFs (default: current directory)")
        parser.add_argument("--dry-run", action="store_true",
                            help="Validate CSV and render first 3 PDFs without saving")

    def handle(self, *args, **options):
        template_name = options["template"]
        csv_path = options["csv_path"]
        actor_username = options["actor"]
        output_dir = Path(options["output_dir"])
        dry_run = options["dry_run"]

        # --- Resolve actor ---
        try:
            actor = User.objects.get(username=actor_username)
        except User.DoesNotExist:
            raise CommandError(f"User '{actor_username}' not found.")

        # --- Resolve template ---
        try:
            template = LetterTemplate.objects.get(name=template_name, is_active=True)
        except LetterTemplate.DoesNotExist:
            raise CommandError(
                f"No active template found for '{template_name}'. "
                "Activate one via the admin panel first."
            )

        # --- Read CSV ---
        if not os.path.exists(csv_path):
            raise CommandError(f"CSV file not found: {csv_path}")

        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        if not rows:
            raise CommandError("CSV file is empty.")

        self.stdout.write(f"Template  : {template}")
        self.stdout.write(f"CSV rows  : {len(rows)}")
        self.stdout.write(f"Actor     : {actor}")
        self.stdout.write(f"Output    : {output_dir}")
        self.stdout.write(f"Dry run   : {dry_run}")
        self.stdout.write("")

        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)

        success, failed, skipped = 0, 0, 0
        errors = []
        limit = 3 if dry_run else len(rows)

        for i, row in enumerate(rows[:limit]):
            employee_code = row.get("employee_code", "").strip()
            if not employee_code:
                errors.append((i + 2, "Missing employee_code"))
                failed += 1
                continue

            try:
                employee = Employee.objects.get(employee_code=employee_code)
            except Employee.DoesNotExist:
                errors.append((i + 2, f"Employee not found: {employee_code}"))
                failed += 1
                continue

            # All CSV columns become variables (except employee_code itself)
            variables = {k: v for k, v in row.items() if k != "employee_code" and v}

            try:
                document, pdf_bytes = generate_document(
                    template_id=template.id,
                    employee_id=employee.id,
                    variables=variables,
                    actor=actor,
                )

                if not dry_run:
                    filename = output_dir / f"{employee_code}_{template_name}.pdf"
                    filename.write_bytes(pdf_bytes)

                success += 1
                self.stdout.write(
                    f"  {'[DRY] ' if dry_run else ''}OK  row {i+2}: {employee.name} ({employee_code})"
                )

            except Exception as exc:
                failed += 1
                errors.append((i + 2, f"{employee_code}: {exc}"))
                self.stdout.write(
                    self.style.WARNING(f"  FAIL row {i+2}: {employee_code} — {exc}")
                )

        # --- Report ---
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Success : {success}")
        self.stdout.write(f"Failed  : {failed}")
        if dry_run and len(rows) > 3:
            self.stdout.write(f"Skipped : {len(rows) - 3} (dry-run limit)")
        if errors:
            self.stdout.write("\nErrors:")
            for row_num, msg in errors:
                self.stdout.write(f"  Row {row_num}: {msg}")
        self.stdout.write("=" * 50)

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                "\nDry run passed. Remove --dry-run to generate all documents."
            ))
