"""
Encrypted document storage service.

All PDF reads/writes route through this module so the rest of the app
never touches raw bytes or storage paths directly.

Encryption: AES-256 via Fernet (symmetric, from the `cryptography` library).
Key source: DOCUMENT_ENCRYPTION_KEY env var — a URL-safe base64-encoded 32-byte key.

Generate a key once with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If DOCUMENT_ENCRYPTION_KEY is not set (dev mode), files are stored unencrypted.
Set it for any environment that handles real employee data.

Future S3 swap: only this file needs updating. Views, models, and pdf_service
are all unaware of the storage backend or encryption layer.
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def _get_fernet():
    """Return a Fernet instance if DOCUMENT_ENCRYPTION_KEY is configured, else None."""
    from decouple import config
    key = config("DOCUMENT_ENCRYPTION_KEY", default="")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def save_document(s3_key: str, pdf_bytes: bytes) -> None:
    """Encrypt (if key configured) and write PDF bytes to storage."""
    fernet = _get_fernet()
    data = fernet.encrypt(pdf_bytes) if fernet else pdf_bytes
    default_storage.save(s3_key, ContentFile(data))


def read_document(s3_key: str) -> bytes:
    """Read PDF bytes from storage and decrypt (if key configured)."""
    fernet = _get_fernet()
    data = default_storage.open(s3_key).read()
    return fernet.decrypt(data) if fernet else data
