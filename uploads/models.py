import uuid
from django.conf import settings
from django.db import models


class UploadedDocument(models.Model):
    TYPE_RECEIPT = "receipt"
    TYPE_PAYMENT_SLIP = "payment_slip"
    TYPE_INVOICE = "invoice"
    TYPE_CONTRACT = "contract"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_RECEIPT, "Receipt"),
        (TYPE_PAYMENT_SLIP, "Payment Slip"),
        (TYPE_INVOICE, "Invoice"),
        (TYPE_CONTRACT, "Contract"),
        (TYPE_OTHER, "Other"),
    ]

    ALLOWED_EXTENSIONS = {
        "pdf", "png", "jpg", "jpeg",
        "xlsx", "xls", "csv",
        "docx", "doc",
    }
    MAX_UPLOAD_SIZE_MB = 20

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    description = models.TextField(blank=True)

    # Optional association with a company (for filtering/organisation)
    company = models.ForeignKey(
        "documents.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_documents",
    )

    # Storage — the actual bytes are written via storage_service (encrypted if key set)
    storage_key = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="Size in bytes")
    content_type = models.CharField(max_length=100, blank=True)

    # Confidential uploads are only visible to the uploader + Finance Head
    is_confidential = models.BooleanField(
        default=False,
        help_text="Restrict visibility to uploader and Finance Head only.",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Uploaded Document"
        verbose_name_plural = "Uploaded Documents"

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) — {self.uploaded_by}"

    @property
    def file_size_display(self):
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 ** 2:.1f} MB"

    @property
    def extension(self):
        return self.original_filename.rsplit(".", 1)[-1].lower() if "." in self.original_filename else ""

    @property
    def is_image(self):
        return self.extension in {"png", "jpg", "jpeg"}

    @property
    def is_pdf(self):
        return self.extension == "pdf"
