from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"

    def ready(self):
        # Install DB-level append-only triggers for AuditEvent after migrations
        from django.db.models.signals import post_migrate
        from documents.signals import install_audit_triggers
        post_migrate.connect(install_audit_triggers, sender=self)
