"""
Management command: reconcile_documents

Daily integrity check: for every Document record, verify that:
  1. The PDF file still exists in storage
  2. The SHA-256 of the stored file matches the recorded content_hash

Run via cron or a scheduled GitHub Action:
    python manage.py reconcile_documents
    python manage.py reconcile_documents --since 2026-01-01
    python manage.py reconcile_documents --document-id <uuid>

Creates AuditEvent records for each mismatch found.
Exits with code 1 if any mismatches are detected (useful for CI alerting).
"""
import hashlib
import sys
from datetime import date

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.models import AuditEvent, Document


def _sha256_of_file(storage_key: str) -> str | None:
    """Return hex SHA-256 of a file in storage, or None if file is missing."""
    try:
        with default_storage.open(storage_key) as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


class Command(BaseCommand):
    help = "Verify stored PDFs match their recorded SHA-256 hashes."

    def add_arguments(self, parser):
        parser.add_argument("--since", type=date.fromisoformat, default=None,
                            help="Only check documents generated on or after this date (YYYY-MM-DD)")
        parser.add_argument("--document-id", dest="document_id", default=None,
                            help="Check a single document by UUID")
        parser.add_argument("--quiet", action="store_true",
                            help="Only print mismatches (suppress OK lines)")

    def handle(self, *args, **options):
        quiet = options["quiet"]
        qs = Document.objects.all().order_by("generated_at")

        if options["document_id"]:
            qs = qs.filter(id=options["document_id"])
        if options["since"]:
            qs = qs.filter(generated_at__date__gte=options["since"])

        total = qs.count()
        self.stdout.write(f"Checking {total} document(s)…\n")

        ok_count = 0
        mismatch_count = 0
        missing_count = 0

        for doc in qs:
            actual_hash = _sha256_of_file(doc.s3_key)

            if actual_hash is None:
                missing_count += 1
                msg = f"  MISSING  {doc.id}  {doc.s3_key}"
                self.stdout.write(self.style.ERROR(msg))
                AuditEvent.objects.create(
                    event_type="reconciliation.mismatch",
                    target_type="Document",
                    target_id=str(doc.id),
                    metadata={
                        "reason": "file_missing",
                        "s3_key": doc.s3_key,
                        "expected_hash": doc.content_hash,
                    },
                )
            elif actual_hash != doc.content_hash:
                mismatch_count += 1
                msg = (
                    f"  MISMATCH {doc.id}\n"
                    f"    expected: {doc.content_hash}\n"
                    f"    actual  : {actual_hash}"
                )
                self.stdout.write(self.style.ERROR(msg))
                AuditEvent.objects.create(
                    event_type="reconciliation.mismatch",
                    target_type="Document",
                    target_id=str(doc.id),
                    metadata={
                        "reason": "hash_mismatch",
                        "s3_key": doc.s3_key,
                        "expected_hash": doc.content_hash,
                        "actual_hash": actual_hash,
                    },
                )
            else:
                ok_count += 1
                if not quiet:
                    self.stdout.write(f"  OK       {doc.id}")
                AuditEvent.objects.create(
                    event_type="reconciliation.ok",
                    target_type="Document",
                    target_id=str(doc.id),
                    metadata={"s3_key": doc.s3_key, "content_hash": doc.content_hash},
                )

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Total     : {total}")
        self.stdout.write(f"OK        : {ok_count}")
        self.stdout.write(f"Missing   : {missing_count}")
        self.stdout.write(f"Mismatch  : {mismatch_count}")
        self.stdout.write("=" * 50)

        if missing_count + mismatch_count > 0:
            self.stdout.write(self.style.ERROR(
                f"\n⚠ {missing_count + mismatch_count} integrity issue(s) found. "
                "AuditEvent records created. Investigate immediately."
            ))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\n✓ All documents verified successfully."))
