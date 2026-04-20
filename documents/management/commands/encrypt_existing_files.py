"""
Management command: encrypt_existing_files

Re-encrypts any plaintext files (generated PDFs and uploaded documents) that
were written to storage before DOCUMENT_ENCRYPTION_KEY was set.

Safe to run multiple times — already-encrypted files are detected by attempting
Fernet decryption and skipped if they succeed.

Usage:
    python manage.py encrypt_existing_files
    python manage.py encrypt_existing_files --dry-run   # report only, no writes
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


def _get_fernet():
    from decouple import config
    key = config("DOCUMENT_ENCRYPTION_KEY", default="")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def _is_encrypted(fernet, raw_bytes: bytes) -> bool:
    """Return True if raw_bytes is already a valid Fernet token."""
    try:
        fernet.decrypt(raw_bytes)
        return True
    except Exception:
        return False


def _encrypt_file(fernet, storage_key: str, dry_run: bool) -> str:
    """
    Read the file at storage_key, encrypt if needed, overwrite in place.
    Returns one of: 'encrypted', 'already_encrypted', 'missing', 'error'.
    """
    try:
        raw = default_storage.open(storage_key).read()
    except FileNotFoundError:
        return "missing"
    except Exception:
        return "error"

    if _is_encrypted(fernet, raw):
        return "already_encrypted"

    if dry_run:
        return "would_encrypt"

    encrypted = fernet.encrypt(raw)
    # Delete then re-save to overwrite in place (works for both local and S3)
    default_storage.delete(storage_key)
    default_storage.save(storage_key, ContentFile(encrypted))
    return "encrypted"


class Command(BaseCommand):
    help = "Encrypt existing unencrypted files in storage using DOCUMENT_ENCRYPTION_KEY"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be done without making any changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        fernet = _get_fernet()
        if fernet is None:
            raise CommandError(
                "DOCUMENT_ENCRYPTION_KEY is not set. "
                "Generate one with:\n"
                "  python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"\n"
                "then add it to your .env file."
            )

        from documents.models import Document
        from uploads.models import UploadedDocument

        counters = {
            "encrypted": 0,
            "already_encrypted": 0,
            "missing": 0,
            "would_encrypt": 0,
            "error": 0,
        }

        # --- Generated PDF documents ---
        self.stdout.write("\n📄  Scanning generated PDF documents...")
        docs = Document.objects.values_list("id", "s3_key")
        for doc_id, key in docs:
            status = _encrypt_file(fernet, key, dry_run)
            counters[status] = counters.get(status, 0) + 1
            label = {
                "encrypted": self.style.SUCCESS("✓ encrypted"),
                "would_encrypt": self.style.WARNING("~ would encrypt"),
                "already_encrypted": "  already encrypted",
                "missing": self.style.ERROR("✗ file missing"),
                "error": self.style.ERROR("✗ error reading"),
            }.get(status, status)
            self.stdout.write(f"  {key}  [{label}]")

        # --- Uploaded documents ---
        self.stdout.write("\n📁  Scanning uploaded documents...")
        uploads = UploadedDocument.objects.values_list("id", "storage_key")
        for up_id, key in uploads:
            status = _encrypt_file(fernet, key, dry_run)
            counters[status] = counters.get(status, 0) + 1
            label = {
                "encrypted": self.style.SUCCESS("✓ encrypted"),
                "would_encrypt": self.style.WARNING("~ would encrypt"),
                "already_encrypted": "  already encrypted",
                "missing": self.style.ERROR("✗ file missing"),
                "error": self.style.ERROR("✗ error reading"),
            }.get(status, status)
            self.stdout.write(f"  {key}  [{label}]")

        # --- Summary ---
        self.stdout.write("\n" + "─" * 50)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no files were modified"))
            self.stdout.write(f"  Files that would be encrypted : {counters['would_encrypt']}")
            self.stdout.write(f"  Already encrypted             : {counters['already_encrypted']}")
        else:
            self.stdout.write(self.style.SUCCESS("Done."))
            self.stdout.write(f"  Newly encrypted : {counters['encrypted']}")
            self.stdout.write(f"  Already done    : {counters['already_encrypted']}")
        if counters["missing"]:
            self.stdout.write(self.style.ERROR(f"  Missing files   : {counters['missing']}"))
        if counters["error"]:
            self.stdout.write(self.style.ERROR(f"  Errors          : {counters['error']}"))
        self.stdout.write("")
