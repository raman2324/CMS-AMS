from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0006_lettertemplate_free_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add ContractLens event types to AuditEvent choices (no DB schema change needed)
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("document.generated", "Document Generated"),
                    ("document.downloaded", "Document Downloaded"),
                    ("document.voided", "Document Voided"),
                    ("document.viewed", "Document Viewed"),
                    ("document.access_denied", "Document Access Denied"),
                    ("document.locked", "Document Locked"),
                    ("document.unlocked", "Document Unlocked"),
                    ("document.generation_failed", "Document Generation Failed"),
                    ("template.published", "Template Published"),
                    ("user.role_changed", "User Role Changed"),
                    ("audit.flag.template_issuer_overlap", "Template-Issuer Overlap Flag"),
                    ("reconciliation.mismatch", "Reconciliation Mismatch"),
                    ("reconciliation.ok", "Reconciliation OK"),
                    ("upload.created", "File Uploaded"),
                    ("upload.viewed", "File Viewed"),
                    ("upload.downloaded", "File Downloaded"),
                    ("upload.deleted", "File Deleted"),
                    ("contractlens.extracted", "ContractLens: PDF Extracted"),
                    ("contractlens.group_analysed", "ContractLens: Group Analysed"),
                    ("contractlens.merged", "ContractLens: Contracts Merged"),
                ],
                db_index=True,
                max_length=100,
            ),
        ),
        # Create ContractLensRecord table
        migrations.CreateModel(
            name="ContractLensRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("frontend_id", models.CharField(blank=True, db_index=True, max_length=60)),
                ("customer_name", models.CharField(blank=True, max_length=500)),
                ("record_type", models.CharField(
                    choices=[
                        ("extract", "Single PDF Extraction"),
                        ("group", "Document Group Analysis"),
                        ("merge", "Merged Contracts"),
                    ],
                    default="extract",
                    max_length=20,
                )),
                ("is_group", models.BooleanField(default=False)),
                ("contract_data", models.TextField(default=dict)),
                ("source_files_meta", models.TextField(default=list)),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="contractlens_records",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "ContractLens Record",
                "ordering": ["-created_at"],
            },
        ),
    ]
