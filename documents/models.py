"""
Core data models for the HR Document Generation Platform.

Model hierarchy:
  Company  ──< Employee ──< Document >── LetterTemplate
                                 │
                             AuditEvent  (append-only, guarded by DB triggers)
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from documents.fields import EncryptedDecimalField, EncryptedJSONField


# ---------------------------------------------------------------------------
# Shared schema constants
# ---------------------------------------------------------------------------

# Fields present on every generated letter regardless of template type.
# The generate form always shows these; template-specific fields are additive.
BASE_VARIABLES_SCHEMA = {
    "issue_date": {"type": "date", "label": "Issue Date", "required": True},
    "ref_number": {"type": "text", "label": "Reference Number", "required": False},
}

TEMPLATE_NAME_CHOICES = [
    ("offer_letter", "Offer Letter"),
    ("salary_letter", "Salary Letter"),
    ("noc", "No Objection Certificate"),
    ("experience_certificate", "Experience Certificate"),
]

# Per-template extra field schemas — merged with BASE_VARIABLES_SCHEMA at runtime.
TEMPLATE_EXTRA_SCHEMAS = {
    "offer_letter": {
        "ctc_annual": {"type": "number", "label": "Annual CTC (INR)", "required": True},
        "start_date": {"type": "date", "label": "Start Date", "required": True},
        "probation_months": {"type": "number", "label": "Probation Period (months)", "required": False, "default": "3"},
        "reporting_to": {"type": "text", "label": "Reporting To", "required": True},
        "work_location": {"type": "text", "label": "Work Location", "required": True},
    },
    "salary_letter": {
        "salary_monthly": {"type": "number", "label": "Monthly Gross Salary (INR)", "required": True},
        "salary_annual": {"type": "number", "label": "Annual CTC (INR)", "required": True},
        "effective_date": {"type": "date", "label": "Effective From", "required": True},
        "basic": {"type": "number", "label": "Basic Salary (INR)", "required": False},
        "hra": {"type": "number", "label": "HRA (INR)", "required": False},
    },
    "noc": {
        "purpose": {"type": "text", "label": "Purpose of NOC", "required": True},
        "valid_until": {"type": "date", "label": "Valid Until (optional)", "required": False},
    },
    "experience_certificate": {
        "last_working_date": {"type": "date", "label": "Last Working Date", "required": True},
        "performance_note": {"type": "text", "label": "Performance Note (optional)", "required": False},
    },
}


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    short_name = models.SlugField(max_length=50, unique=True)
    registered_address = models.TextField(help_text="Full registered address as it appears on letters.")
    cin = models.CharField(max_length=21, verbose_name="CIN", help_text="Corporate Identification Number")
    gstin = models.CharField(max_length=15, blank=True, verbose_name="GSTIN")
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    signatory_name = models.CharField(max_length=200)
    signatory_designation = models.CharField(max_length=200, help_text='e.g. "Director, HR"')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class Employee(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_HRIS = "hris"
    SOURCE_CHOICES = [(SOURCE_MANUAL, "Manual"), (SOURCE_HRIS, "HRIS Sync")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="employees")
    name = models.CharField(max_length=200)
    email = models.EmailField()
    employee_code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=200)
    role = models.CharField(max_length=200, help_text="Job role / function")
    department = models.CharField(max_length=200)
    joining_date = models.DateField()
    salary_current = EncryptedDecimalField(
        null=True, blank=True,
        help_text="Current monthly gross salary (INR). Used as default in salary letters."
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    # Reserved for future HRIS sync (Darwinbox / Zoho / GreytHR)
    source_system_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["company", "name"]

    def __str__(self):
        return f"{self.name} ({self.employee_code})"


# ---------------------------------------------------------------------------
# LetterTemplate
# ---------------------------------------------------------------------------

class LetterTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=TEMPLATE_NAME_CHOICES)
    version = models.PositiveIntegerField(default=1, editable=False)
    html_content = models.TextField(
        help_text="Django template syntax. Variables: {{ company }}, {{ employee }}, {{ issue_date }}, etc."
    )
    # Template-specific extra fields only. Base fields (issue_date, ref_number)
    # are always included automatically — don't duplicate them here.
    extra_variables_schema = models.JSONField(
        default=dict,
        help_text="JSON schema for template-specific form fields. See TEMPLATE_EXTRA_SCHEMAS in models.py."
    )
    is_active = models.BooleanField(
        default=False,
        help_text="Only one version per template name can be active at a time."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_templates",
    )

    class Meta:
        unique_together = [("name", "version")]
        ordering = ["name", "-version"]
        verbose_name = "Letter Template"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.get_name_display()} v{self.version} ({status})"

    def save(self, *args, **kwargs):
        if self._state.adding:
            # Auto-increment version number for this template name
            last = LetterTemplate.objects.filter(name=self.name).order_by("-version").first()
            self.version = (last.version + 1) if last else 1
        super().save(*args, **kwargs)

    def activate(self):
        """Activate this version, deactivating any previously active version."""
        LetterTemplate.objects.filter(name=self.name, is_active=True).update(is_active=False)
        self.is_active = True
        self.save(update_fields=["is_active"])

    @property
    def full_schema(self):
        """Merged schema: base variables + template-specific extras."""
        return {**BASE_VARIABLES_SCHEMA, **self.extra_variables_schema}


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(models.Model):
    STATUS_GENERATED = "generated"
    STATUS_VOID = "void"
    STATUS_CHOICES = [
        (STATUS_GENERATED, "Generated"),
        (STATUS_VOID, "Void"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="documents")
    template = models.ForeignKey(LetterTemplate, on_delete=models.PROTECT, related_name="documents")
    recipient = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="documents")
    # Full snapshot of every value used to render the PDF — immutable record
    variables_snapshot = EncryptedJSONField()
    # Storage key (relative path for filesystem; S3 key for cloud)
    s3_key = models.CharField(max_length=500)
    # SHA-256 hex digest of the raw PDF bytes
    content_hash = models.CharField(max_length=64)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_documents",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_GENERATED)
    download_count = models.IntegerField(default=0)

    # Legal hold / document lock — Finance Head only
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="locked_documents",
    )
    locked_reason = models.CharField(max_length=500, blank=True)
    # Stub for future email delivery — populated when email is sent to employee
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.template.get_name_display()} — {self.recipient.name} ({self.generated_at.strftime('%Y-%m-%d')})"

    @property
    def is_void(self):
        return self.status == self.STATUS_VOID


# ---------------------------------------------------------------------------
# AuditEvent  (append-only — enforced by DB triggers in signals.py)
# ---------------------------------------------------------------------------

class AuditEvent(models.Model):
    EVENT_TYPES = [
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
        # Other Documents (uploads) events
        ("upload.created", "File Uploaded"),
        ("upload.viewed", "File Viewed"),
        ("upload.downloaded", "File Downloaded"),
        ("upload.deleted", "File Deleted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=100, choices=EVENT_TYPES, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    content_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),
        ]
        verbose_name = "Audit Event"

    def __str__(self):
        actor_str = str(self.actor) if self.actor else "system"
        return f"{self.event_type} by {actor_str} @ {self.occurred_at.strftime('%Y-%m-%d %H:%M')}"

    # Application-layer guard (DB triggers are the real enforcement)
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("AuditEvent records are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditEvent records are immutable and cannot be deleted.")
