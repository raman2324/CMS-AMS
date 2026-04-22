"""
DB-level append-only protection for AuditEvent.
Creates triggers on first migrate and after each migration run.
Triggers are idempotent (DROP IF EXISTS + CREATE).
"""
from django.db import connection


def install_audit_triggers(sender, **kwargs):
    """
    Install DB triggers that prevent UPDATE/DELETE on documents_auditevent.
    Supports both SQLite and PostgreSQL.
    """
    vendor = connection.vendor

    with connection.cursor() as cursor:
        if vendor == "sqlite":
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS prevent_audit_update
                BEFORE UPDATE ON documents_auditevent
                BEGIN
                    SELECT RAISE(ABORT, 'AuditEvent records are immutable and cannot be updated');
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
                BEFORE DELETE ON documents_auditevent
                BEGIN
                    SELECT RAISE(ABORT, 'AuditEvent records are immutable and cannot be deleted');
                END;
            """)

        elif vendor == "postgresql":
            cursor.execute("""
                CREATE OR REPLACE FUNCTION prevent_audit_modification()
                RETURNS TRIGGER AS $$
                BEGIN
                    RAISE EXCEPTION 'AuditEvent records are immutable and cannot be modified or deleted';
                END;
                $$ LANGUAGE plpgsql;
            """)
            cursor.execute("""
                DROP TRIGGER IF EXISTS audit_event_immutable ON documents_auditevent;
            """)
            cursor.execute("""
                CREATE TRIGGER audit_event_immutable
                BEFORE UPDATE OR DELETE ON documents_auditevent
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();
            """)

        elif vendor == "mysql":
            cursor.execute("DROP TRIGGER IF EXISTS prevent_audit_update")
            cursor.execute("""
                CREATE TRIGGER prevent_audit_update
                BEFORE UPDATE ON documents_auditevent
                FOR EACH ROW
                BEGIN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'AuditEvent records are immutable and cannot be updated';
                END
            """)
            cursor.execute("DROP TRIGGER IF EXISTS prevent_audit_delete")
            cursor.execute("""
                CREATE TRIGGER prevent_audit_delete
                BEFORE DELETE ON documents_auditevent
                FOR EACH ROW
                BEGIN
                    SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'AuditEvent records are immutable and cannot be deleted';
                END
            """)
