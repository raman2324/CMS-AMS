"""
Upload storage service — mirrors documents/services/storage_service.py.

All file reads/writes for uploaded documents route through here so the rest
of the app never touches raw bytes or storage paths directly.

Uses the same DOCUMENT_ENCRYPTION_KEY env var as the PDF service, meaning
uploaded files get the same AES-256 encryption at rest.
"""
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import UploadedDocument


def _log(event_type: str, actor, doc: "UploadedDocument", extra: dict = None):
    from documents.models import AuditEvent
    AuditEvent.objects.create(
        event_type=event_type,
        actor=actor,
        target_type="UploadedDocument",
        target_id=str(doc.id),
        metadata={
            "title": doc.title,
            "doc_type": doc.document_type,
            "doc_type_display": doc.get_document_type_display(),
            "original_filename": doc.original_filename,
            **(extra or {}),
        },
    )


def _get_fernet():
    from decouple import config
    key = config("DOCUMENT_ENCRYPTION_KEY", default="")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def _build_storage_key(document_type: str, original_filename: str, doc_id: str) -> str:
    from django.utils import timezone
    now = timezone.now()
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
    return f"uploads/{document_type}/{now.year}/{now.month:02d}/{doc_id}.{ext}"


def save_upload(file_bytes: bytes, document_type: str, original_filename: str, doc_id: str) -> str:
    """Encrypt (if key configured) and write file bytes. Returns the storage key."""
    storage_key = _build_storage_key(document_type, original_filename, doc_id)
    fernet = _get_fernet()
    data = fernet.encrypt(file_bytes) if fernet else file_bytes
    default_storage.save(storage_key, ContentFile(data))
    return storage_key


def read_upload(storage_key: str) -> bytes:
    """Read and decrypt (if key configured) file bytes from storage."""
    fernet = _get_fernet()
    data = default_storage.open(storage_key).read()
    return fernet.decrypt(data) if fernet else data


def delete_upload(storage_key: str) -> None:
    """Delete file from storage (used when a document record is deleted)."""
    if default_storage.exists(storage_key):
        default_storage.delete(storage_key)


def create_uploaded_document(
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
    title: str,
    document_type: str,
    description: str,
    company,
    is_confidential: bool,
    actor,
) -> "UploadedDocument":
    """Persist file bytes + create the UploadedDocument record."""
    doc_id = str(uuid.uuid4())
    storage_key = save_upload(file_bytes, document_type, original_filename, doc_id)

    doc = UploadedDocument.objects.create(
        id=doc_id,
        title=title,
        document_type=document_type,
        description=description,
        company=company,
        storage_key=storage_key,
        original_filename=original_filename,
        file_size=len(file_bytes),
        content_type=content_type,
        is_confidential=is_confidential,
        uploaded_by=actor,
    )
    _log("upload.created", actor, doc, {
        "file_size": doc.file_size,
        "is_confidential": is_confidential,
    })
    return doc


def log_view(doc: "UploadedDocument", actor) -> None:
    _log("upload.viewed", actor, doc)


def log_download(doc: "UploadedDocument", actor) -> None:
    _log("upload.downloaded", actor, doc)


def log_delete(doc: "UploadedDocument", actor) -> None:
    _log("upload.deleted", actor, doc)
