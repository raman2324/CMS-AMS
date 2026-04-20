import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("documents", "0003_document_email_sent_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UploadedDocument",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("document_type", models.CharField(
                    choices=[
                        ("receipt", "Receipt"),
                        ("payment_slip", "Payment Slip"),
                        ("invoice", "Invoice"),
                        ("contract", "Contract"),
                        ("other", "Other"),
                    ],
                    default="other",
                    max_length=20,
                )),
                ("description", models.TextField(blank=True)),
                ("storage_key", models.CharField(max_length=500)),
                ("original_filename", models.CharField(max_length=255)),
                ("file_size", models.PositiveIntegerField(help_text="Size in bytes")),
                ("content_type", models.CharField(blank=True, max_length=100)),
                ("is_confidential", models.BooleanField(
                    default=False,
                    help_text="Restrict visibility to uploader and Finance Head only.",
                )),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="uploaded_documents",
                    to="documents.company",
                )),
                ("uploaded_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="uploaded_documents",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Uploaded Document",
                "verbose_name_plural": "Uploaded Documents",
                "ordering": ["-uploaded_at"],
            },
        ),
    ]
