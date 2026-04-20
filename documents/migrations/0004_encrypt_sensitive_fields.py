"""
Migration 0004: Encrypt sensitive fields at the database level.

Schema changes:
  - Employee.salary_current  : DecimalField  → EncryptedDecimalField (stored as TEXT)
  - Document.variables_snapshot : JSONField  → EncryptedJSONField   (stored as TEXT)

Data migration (RunPython):
  - If DOCUMENT_ENCRYPTION_KEY is set, encrypts all existing plaintext values.
  - If the key is NOT set, the migration is a no-op for data (schema still applies).
  - The reverse function decrypts back to plaintext (useful for rollback testing).

Fallback safety:
  The field's from_db_value() always tries decryption first and falls back to
  treating the value as plaintext on InvalidToken — so rows written before this
  migration can still be read safely during the transition window.
"""
import json
from decimal import Decimal

from django.db import migrations

import documents.fields


# ---------------------------------------------------------------------------
# Data migration helpers
# ---------------------------------------------------------------------------

def _fernet():
    try:
        from decouple import config
        key = config("DOCUMENT_ENCRYPTION_KEY", default="")
    except Exception:
        key = ""
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def _is_already_encrypted(value: str) -> bool:
    """
    Fernet tokens are URL-safe base64 and always start with 'gAAAAA' when
    the raw bytes are base64-decoded. A JSON object starts with '{' and a
    decimal string starts with a digit or '-'. This heuristic is safe enough
    for our data set.
    """
    if not value:
        return False
    # Fernet tokens are long base64 strings with no spaces or braces
    return len(value) > 80 and value.startswith("gAAAAA")


def encrypt_existing_data(apps, schema_editor):
    """Encrypt plaintext values that exist before this migration runs."""
    fernet = _fernet()
    if fernet is None:
        return  # Key not set — leave data as-is (still readable via fallback)

    db = schema_editor.connection

    # --- variables_snapshot (JSON stored as TEXT) ---
    with db.cursor() as cursor:
        cursor.execute("SELECT id, variables_snapshot FROM documents_document")
        rows = cursor.fetchall()

    with db.cursor() as cursor:
        for doc_id, snapshot in rows:
            if not snapshot or _is_already_encrypted(snapshot):
                continue
            encrypted = fernet.encrypt(snapshot.encode()).decode()
            cursor.execute(
                "UPDATE documents_document SET variables_snapshot = %s WHERE id = %s",
                [encrypted, str(doc_id)],
            )

    # --- salary_current (stored as TEXT after AlterField) ---
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, salary_current FROM documents_employee WHERE salary_current IS NOT NULL"
        )
        rows = cursor.fetchall()

    with db.cursor() as cursor:
        for emp_id, salary in rows:
            if not salary:
                continue
            str_val = str(salary).strip()
            if _is_already_encrypted(str_val):
                continue
            encrypted = fernet.encrypt(str_val.encode()).decode()
            cursor.execute(
                "UPDATE documents_employee SET salary_current = %s WHERE id = %s",
                [encrypted, str(emp_id)],
            )


def decrypt_existing_data(apps, schema_editor):
    """Reverse: decrypt ciphertext back to plaintext (for rollback)."""
    fernet = _fernet()
    if fernet is None:
        return

    from cryptography.fernet import InvalidToken
    db = schema_editor.connection

    # --- variables_snapshot ---
    with db.cursor() as cursor:
        cursor.execute("SELECT id, variables_snapshot FROM documents_document")
        rows = cursor.fetchall()

    with db.cursor() as cursor:
        for doc_id, snapshot in rows:
            if not snapshot or not _is_already_encrypted(snapshot):
                continue
            try:
                plaintext = fernet.decrypt(snapshot.encode()).decode()
            except InvalidToken:
                continue
            cursor.execute(
                "UPDATE documents_document SET variables_snapshot = %s WHERE id = %s",
                [plaintext, str(doc_id)],
            )

    # --- salary_current ---
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, salary_current FROM documents_employee WHERE salary_current IS NOT NULL"
        )
        rows = cursor.fetchall()

    with db.cursor() as cursor:
        for emp_id, salary in rows:
            if not salary:
                continue
            str_val = str(salary).strip()
            if not _is_already_encrypted(str_val):
                continue
            try:
                plaintext = fernet.decrypt(str_val.encode()).decode()
            except InvalidToken:
                continue
            cursor.execute(
                "UPDATE documents_employee SET salary_current = %s WHERE id = %s",
                [plaintext, str(emp_id)],
            )


# ---------------------------------------------------------------------------
# Migration definition
# ---------------------------------------------------------------------------

class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_document_email_sent_at"),
    ]

    operations = [
        # 1. Change variables_snapshot from JSONField to EncryptedJSONField.
        #    Both are stored as TEXT in the DB, so no column type change in SQLite.
        #    For PostgreSQL (jsonb → text) a manual ALTER COLUMN is needed before
        #    running this migration in production for the first time.
        migrations.AlterField(
            model_name="document",
            name="variables_snapshot",
            field=documents.fields.EncryptedJSONField(),
        ),

        # 2. Change salary_current from DecimalField to EncryptedDecimalField.
        #    Column type changes from NUMERIC → TEXT; Django recreates the table
        #    in SQLite and ALTERs the column in PostgreSQL/MySQL.
        migrations.AlterField(
            model_name="employee",
            name="salary_current",
            field=documents.fields.EncryptedDecimalField(
                blank=True,
                null=True,
                help_text="Current monthly gross salary (INR). Used as default in salary letters.",
            ),
        ),

        # 3. Encrypt any existing plaintext values written before this migration.
        migrations.RunPython(
            encrypt_existing_data,
            reverse_code=decrypt_existing_data,
        ),
    ]
