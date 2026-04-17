"""
Core document generation service.

Public API:
    generate_document(template_id, employee_id, variables, actor) -> (Document, bytes)
    void_document(document_id, actor, reason) -> Document
    download_document(document_id, actor) -> bytes
    build_letter_context(company, employee, variables) -> dict
    render_letter_html(template, context) -> str
"""
import hashlib
import uuid as _uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models as db_models
from django.template import Template, Context
from django.utils import timezone

from documents.models import Document, AuditEvent, LetterTemplate, Employee, Company


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def build_letter_context(company: Company, employee: Employee, variables: dict) -> dict:
    """
    Assemble the full template rendering context.
    company.* and employee.* are available as dicts in the template.
    All user-provided variables are merged at the top level.
    """
    return {
        "company": {
            "name": company.name,
            "short_name": company.short_name,
            "registered_address": company.registered_address,
            "cin": company.cin,
            "gstin": company.gstin,
            "signatory_name": company.signatory_name,
            "signatory_designation": company.signatory_designation,
        },
        "employee": {
            "name": employee.name,
            "email": employee.email,
            "employee_code": employee.employee_code,
            "designation": employee.designation,
            "role": employee.role,
            "department": employee.department,
            "joining_date": employee.joining_date.strftime("%B %d, %Y") if employee.joining_date else "",
            "salary_current": (
                f"{employee.salary_current:,.2f}" if employee.salary_current else ""
            ),
        },
        **variables,
    }


def render_letter_html(template: LetterTemplate, context_data: dict) -> str:
    """Render the letter's html_content (Django template syntax) with context."""
    django_template = Template(template.html_content)
    ctx = Context(context_data)
    return django_template.render(ctx)


def _generate_pdf_bytes(html_content: str) -> bytes:
    """Convert rendered HTML string to PDF bytes via WeasyPrint."""
    from weasyprint import HTML, CSS

    base_css = CSS(string="""
        @page {
            size: A4;
            margin: 2.5cm 2.5cm 3cm 2.5cm;
        }
        body {
            font-family: "Liberation Serif", "Times New Roman", serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #111;
        }
        p { margin: 0 0 0.6em 0; }
        table { border-collapse: collapse; width: 100%; }
        td, th { padding: 4pt 8pt; }
    """)
    return HTML(string=html_content).write_pdf(stylesheets=[base_css])


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def generate_document(template_id, employee_id, variables: dict, actor) -> tuple:
    """
    Generate a letter PDF and persist everything.

    Steps:
      1. Load template + employee (validates they exist and template is active)
      2. Idempotency guard — return existing doc if same actor/template/employee
         generated within the last 30 seconds (prevents double-click duplicates)
      3. Render HTML → PDF → SHA-256
      4. Save PDF to default_storage (filesystem in dev, S3 in prod)
      5. Create Document record with full variables snapshot
      6. Create AuditEvent
      7. Flag Admin-Issuer overlap if applicable

    Returns: (Document, pdf_bytes)
    Raises:  Any exception from template rendering or storage is propagated
             after writing a document.generation_failed AuditEvent.
    """
    template = LetterTemplate.objects.get(id=template_id, is_active=True)
    employee = Employee.objects.select_related("company").get(id=employee_id)
    company = employee.company

    # --- Idempotency guard ---
    recent_cutoff = timezone.now() - timezone.timedelta(seconds=30)
    duplicate = Document.objects.filter(
        template=template,
        recipient=employee,
        generated_by=actor,
        generated_at__gte=recent_cutoff,
        status=Document.STATUS_GENERATED,
    ).first()
    if duplicate:
        pdf_bytes = default_storage.open(duplicate.s3_key).read()
        return duplicate, pdf_bytes

    # --- Render ---
    context = build_letter_context(company, employee, variables)
    try:
        html_content = render_letter_html(template, context)
        pdf_bytes = _generate_pdf_bytes(html_content)
    except Exception as exc:
        AuditEvent.objects.create(
            event_type="document.generation_failed",
            actor=actor,
            target_type="LetterTemplate",
            target_id=str(template.id),
            metadata={"error": str(exc), "employee_id": str(employee.id)},
        )
        raise

    content_hash = _compute_sha256(pdf_bytes)

    # --- Storage ---
    now = timezone.now()
    doc_id = _uuid.uuid4()
    s3_key = f"documents/{template.name}/{now.year}/{now.month:02d}/{doc_id}.pdf"
    default_storage.save(s3_key, ContentFile(pdf_bytes))

    # --- Snapshot — everything used to render, frozen at generation time ---
    variables_snapshot = {
        "variables": variables,
        "company_snapshot": {
            "name": company.name,
            "registered_address": company.registered_address,
            "cin": company.cin,
            "signatory_name": company.signatory_name,
            "signatory_designation": company.signatory_designation,
        },
        "employee_snapshot": {
            "name": employee.name,
            "designation": employee.designation,
            "department": employee.department,
            "joining_date": str(employee.joining_date),
        },
        "template_version": template.version,
    }

    # --- Persist ---
    document = Document.objects.create(
        id=doc_id,
        company=company,
        template=template,
        recipient=employee,
        variables_snapshot=variables_snapshot,
        s3_key=s3_key,
        content_hash=content_hash,
        generated_by=actor,
    )

    AuditEvent.objects.create(
        event_type="document.generated",
        actor=actor,
        target_type="Document",
        target_id=str(document.id),
        content_hash=content_hash,
        metadata={
            "template_id": str(template.id),
            "template_name": template.name,
            "template_version": template.version,
            "employee_id": str(employee.id),
            "employee_code": employee.employee_code,
        },
    )

    # --- Admin-Issuer overlap flag ---
    from accounts.models import User
    if actor.role == User.ROLE_ADMIN:
        overlap_window = timezone.now() - timezone.timedelta(hours=24)
        if template.created_at >= overlap_window:
            AuditEvent.objects.create(
                event_type="audit.flag.template_issuer_overlap",
                actor=actor,
                target_type="Document",
                target_id=str(document.id),
                metadata={
                    "template_id": str(template.id),
                    "note": "Admin generated a document within 24h of creating/editing this template.",
                },
            )

    return document, pdf_bytes


def void_document(document_id, actor, reason: str) -> Document:
    """
    Mark a document as void. The S3 object is NOT deleted — Object Lock
    retention prevents deletion for compliance. Only the status changes.
    Idempotent: voiding an already-void document returns it unchanged.
    """
    document = Document.objects.get(id=document_id)
    if document.is_void:
        return document

    document.status = Document.STATUS_VOID
    document.save(update_fields=["status"])

    AuditEvent.objects.create(
        event_type="document.voided",
        actor=actor,
        target_type="Document",
        target_id=str(document.id),
        content_hash=document.content_hash,
        metadata={"reason": reason},
    )
    return document


def download_document(document_id, actor) -> bytes:
    """
    Retrieve PDF bytes from storage, increment download counter, log audit event.
    """
    document = Document.objects.get(id=document_id)
    pdf_bytes = default_storage.open(document.s3_key).read()

    Document.objects.filter(id=document_id).update(
        download_count=db_models.F("download_count") + 1
    )
    document.refresh_from_db(fields=["download_count"])

    AuditEvent.objects.create(
        event_type="document.downloaded",
        actor=actor,
        target_type="Document",
        target_id=str(document_id),
        content_hash=document.content_hash,
        metadata={"download_count": document.download_count},
    )
    return pdf_bytes
