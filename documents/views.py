"""
Views for the HR Document Generation Platform.

Routes:
  GET  /documents/                  DocumentListView
  GET  /documents/audit/            AuditLogView (Finance Head + Viewer only)
  GET  /documents/generate/         GenerateDocumentView
  POST /documents/generate/         GenerateDocumentView (generate PDF)
  GET  /documents/<uuid>/           DocumentDetailView
  POST /documents/<uuid>/           DocumentDetailView (void / lock / unlock)
  POST /documents/<uuid>/lock/      document_lock
  POST /documents/<uuid>/unlock/    document_unlock
  GET  /documents/<uuid>/download/  document_download

HTMX endpoints (return HTML fragments):
  GET  /documents/api/employees/              employee_search
  GET  /documents/api/template-fields/<uuid>/ template_fields
  POST /documents/api/preview/               preview_letter

Access control rules:
  - Viewer:       list (metadata only, no download button), detail (no download/void/lock)
  - Issuer:       list (own documents only), detail (own docs only — 403 otherwise)
  - Finance Head: list (all documents), detail (all docs, lock/unlock, void any)
  - Admin:        generate documents, manage templates — NO document read access
"""
import base64
import json
import re
import uuid as _uuid_mod
from datetime import date

import anthropic
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from accounts.models import User
from documents.forms import GenerateDocumentForm, VoidDocumentForm
from documents.models import (
    AuditEvent, Company, ContractLensRecord, Document, Employee,
    LetterTemplate, BASE_VARIABLES_SCHEMA, TEMPLATE_NAME_CHOICES,
)
from documents.services import (
    build_letter_context, download_document, generate_document,
    lock_document, render_letter_html, unlock_document, void_document,
)
from documents.services.storage_service import save_document


# ---------------------------------------------------------------------------
# Access control helpers
# ---------------------------------------------------------------------------

def _assert_document_access(request, document):
    """
    Raise PermissionDenied if the requesting user cannot access this document.
    Finance Head sees everything. Issuers see only their own documents.
    Admins have no document access at all.
    Viewers can see detail/metadata but not download/void — callers handle that.

    Logs document.access_denied audit event before raising.
    """
    user = request.user

    # Admin (IT/DevOps) role has no document access
    if user.role == User.ROLE_ADMIN:
        AuditEvent.objects.create(
            event_type="document.access_denied",
            actor=user,
            target_type="Document",
            target_id=str(document.id),
            metadata={"reason": "admin_role_no_document_access"},
        )
        raise PermissionDenied

    # Finance Head sees all — no further check needed
    if user.sees_all_documents():
        return

    # Viewer sees all document metadata (download/void restricted separately)
    if user.role == User.ROLE_VIEWER:
        return

    # Issuer: only their own documents
    if user.role == User.ROLE_FINANCE_EXECUTIVE and document.generated_by != user:
        AuditEvent.objects.create(
            event_type="document.access_denied",
            actor=user,
            target_type="Document",
            target_id=str(document.id),
            metadata={"reason": "not_owner", "owner": str(document.generated_by_id)},
        )
        raise PermissionDenied


# ---------------------------------------------------------------------------
# HTMX partial endpoints
# ---------------------------------------------------------------------------

@login_required
def employee_search(request):
    """
    HTMX: live employee search.
    Triggered by keyup on the employee name input.
    Returns an HTML fragment with matching employees.
    """
    q = request.GET.get("employee_name", "").strip()
    company_id = request.GET.get("company", "").strip()

    if len(q) < 2:
        return render(request, "documents/partials/employee_results.html", {"employees": []})

    qs = Employee.objects.select_related("company").filter(
        Q(name__icontains=q) | Q(employee_code__icontains=q)
    )
    if company_id:
        qs = qs.filter(company_id=company_id)

    # Issuers scoped to their own department (blank = all departments)
    if request.user.role == User.ROLE_FINANCE_EXECUTIVE and request.user.department:
        qs = qs.filter(department=request.user.department)

    return render(
        request,
        "documents/partials/employee_results.html",
        {"employees": qs[:10]},
    )


@login_required
def template_fields(request, template_id):
    """
    HTMX: render the extra form fields for the selected template.
    Triggered when the user picks a template in the generate form.
    """
    template = get_object_or_404(LetterTemplate, id=template_id, is_active=True)
    schema = template.full_schema  # base + template-specific fields

    # Split schema: regular fields vs. annexure table rows (paired _annual/_monthly)
    regular_fields = {k: v for k, v in schema.items() if v.get("section") != "annexure1"}
    annexure_rows = []
    for k, v in schema.items():
        if v.get("section") != "annexure1" or not k.endswith("_annual"):
            continue
        monthly_key = k[:-7] + "_monthly"
        annexure_rows.append({
            "label": v.get("row_label", v["label"]),
            "annual_name": k,
            "monthly_name": monthly_key,
            "monthly_def": schema.get(monthly_key, {}),
        })

    return render(
        request,
        "documents/partials/template_fields.html",
        {"schema": regular_fields, "annexure_rows": annexure_rows, "template": template},
    )


def _resolve_employee(post, company_id):
    """
    Resolve or create an Employee from POST data.

    If `employee_id` is present → use that existing record.
    Otherwise (manual mode) → get_or_create using emp_code / emp_name from POST.

    Returns Employee or raises ValueError with a human-readable message.
    """
    employee_id = post.get("employee_id", "").strip()
    if employee_id:
        try:
            return Employee.objects.select_related("company").get(id=employee_id)
        except Employee.DoesNotExist:
            raise ValueError("Selected employee not found.")

    # Manual mode
    emp_name = post.get("emp_name", "").strip()
    if not emp_name:
        raise ValueError("Employee name is required.")

    if not company_id:
        raise ValueError("Please select a company.")

    emp_code = post.get("emp_code", "").strip() or f"TEMP-{_uuid_mod.uuid4().hex[:6].upper()}"
    emp_designation = post.get("emp_designation", "").strip() or "—"
    emp_department = post.get("emp_department", "").strip() or "—"
    emp_email = post.get("emp_email", "").strip()

    joining_date_str = post.get("emp_joining_date", "").strip()
    try:
        joining_date = date.fromisoformat(joining_date_str) if joining_date_str else date.today()
    except ValueError:
        joining_date = date.today()

    employee, _ = Employee.objects.get_or_create(
        employee_code=emp_code,
        defaults={
            "company_id": company_id,
            "name": emp_name,
            "email": emp_email,
            "designation": emp_designation,
            "role": emp_designation,
            "department": emp_department,
            "joining_date": joining_date,
        },
    )
    return employee


@login_required
def preview_letter(request):
    """
    HTMX: render an HTML preview of the letter (not a PDF).
    POST is required to receive form variables.
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    template_id = request.POST.get("template")
    company_id = request.POST.get("company", "").strip()

    if not template_id:
        return HttpResponse(
            '<div class="alert alert-warning">Select a template first.</div>'
        )

    try:
        tmpl = LetterTemplate.objects.get(id=template_id, is_active=True)
    except LetterTemplate.DoesNotExist:
        return HttpResponse('<div class="alert alert-danger">Template not found.</div>')

    try:
        employee = _resolve_employee(request.POST, company_id)
    except ValueError as exc:
        return HttpResponse(f'<div class="alert alert-warning">{exc}</div>')

    excluded = {
        "csrfmiddlewaretoken", "template", "employee_id", "company",
        "employee_name", "emp_mode", "emp_name", "emp_code", "emp_email",
        "emp_designation", "emp_department", "emp_joining_date",
    }
    variables = {k: v for k, v in request.POST.items() if k not in excluded}

    try:
        context = build_letter_context(employee.company, employee, variables)
        html_content = render_letter_html(tmpl, context)
    except Exception as exc:
        return HttpResponse(
            f'<div class="alert alert-danger">Preview failed: {exc}</div>'
        )

    return render(
        request,
        "documents/partials/preview.html",
        {"preview_html": html_content},
    )


# ---------------------------------------------------------------------------
# Main views
# ---------------------------------------------------------------------------

class GenerateDocumentView(LoginRequiredMixin, View):
    template_name = "documents/generate.html"

    def get(self, request):
        if not request.user.can_generate():
            messages.error(request, "You do not have permission to generate documents.")
            return redirect("documents:list")
        form = GenerateDocumentForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        if not request.user.can_generate():
            return HttpResponse(status=403)

        template_id = request.POST.get("template")
        company_id = request.POST.get("company", "").strip()

        if not template_id:
            messages.error(request, "Please select a template type.")
            return redirect("documents:generate")

        # Resolve employee (existing record or auto-create from manual fields)
        try:
            employee = _resolve_employee(request.POST, company_id)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("documents:generate")

        # Collect letter variables — everything except form-infrastructure fields
        excluded = {
            "csrfmiddlewaretoken", "template", "employee_id", "company",
            "employee_name", "emp_mode", "emp_name", "emp_code", "emp_email",
            "emp_designation", "emp_department", "emp_joining_date",
        }
        variables = {k: v for k, v in request.POST.items() if k not in excluded}

        try:
            document, pdf_bytes = generate_document(
                template_id=template_id,
                employee_id=employee.id,
                variables=variables,
                actor=request.user,
            )
        except LetterTemplate.DoesNotExist:
            messages.error(request, "Selected template is not active.")
            return redirect("documents:generate")
        except Exception as exc:
            messages.error(request, f"Document generation failed: {exc}")
            return redirect("documents:generate")

        messages.success(
            request,
            f"Document generated successfully for {document.recipient.name}. "
            "You can download it from the Documents list."
        )
        return redirect("documents:list")


class DocumentListView(LoginRequiredMixin, View):
    template_name = "documents/list.html"

    def get(self, request):
        # Admin (IT/DevOps) has no document access
        if request.user.role == User.ROLE_ADMIN:
            messages.error(request, "Admin accounts do not have access to documents.")
            return redirect("ams_approvals:inbox")

        qs = Document.objects.select_related(
            "template", "recipient", "recipient__company", "generated_by"
        )

        # Finance Head sees everything. Issuers see only their own documents.
        if request.user.role == User.ROLE_FINANCE_EXECUTIVE:
            qs = qs.filter(generated_by=request.user)

        # Query filters
        search_query = request.GET.get("q", "").strip()
        if search_query:
            qs = qs.filter(
                Q(recipient__name__icontains=search_query) |
                Q(recipient__employee_code__icontains=search_query) |
                Q(recipient__company__name__icontains=search_query) |
                Q(company__name__icontains=search_query)
            )

        status_filter = request.GET.get("status", "")
        if status_filter:
            qs = qs.filter(status=status_filter)

        template_filter = request.GET.get("template", "")
        if template_filter:
            qs = qs.filter(template__name=template_filter)

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(request.GET.get("page"))

        return render(request, self.template_name, {
            "documents": page_obj,
            "page_obj": page_obj,
            "search_query": search_query,
            "status_filter": status_filter,
            "template_filter": template_filter,
            "template_choices": TEMPLATE_NAME_CHOICES,
            "status_choices": Document.STATUS_CHOICES,
        })


class DocumentDetailView(LoginRequiredMixin, View):
    template_name = "documents/detail.html"

    def _get_document_or_403(self, request, pk):
        document = get_object_or_404(Document, id=pk)
        _assert_document_access(request, document)
        return document

    def get(self, request, pk):
        document = self._get_document_or_403(request, pk)

        # Log every view (Finance Head can see who looked at what)
        AuditEvent.objects.create(
            event_type="document.viewed",
            actor=request.user,
            target_type="Document",
            target_id=str(pk),
            metadata={"role": request.user.role},
        )

        audit_events = AuditEvent.objects.filter(
            target_type="Document", target_id=str(pk)
        ).order_by("occurred_at")
        void_form = VoidDocumentForm()
        return render(request, self.template_name, {
            "document": document,
            "audit_events": audit_events,
            "void_form": void_form,
        })

    def post(self, request, pk):
        """Handle void, lock, and unlock actions."""
        document = self._get_document_or_403(request, pk)
        action = request.POST.get("action", "void")

        if action == "lock":
            return self._handle_lock(request, document)
        elif action == "unlock":
            return self._handle_unlock(request, document)
        else:
            return self._handle_void(request, document, pk)

    def _handle_void(self, request, document, pk):
        # Viewers cannot void
        if request.user.role == User.ROLE_VIEWER:
            raise PermissionDenied

        # Locked documents cannot be voided (even by Finance Head)
        if document.is_locked:
            messages.error(request, "Cannot void a locked document. Unlock it first.")
            return redirect("documents:detail", pk=pk)

        # Issuers can only void their own documents
        if request.user.role == User.ROLE_FINANCE_EXECUTIVE and document.generated_by != request.user:
            raise PermissionDenied

        void_form = VoidDocumentForm(request.POST)
        if not void_form.is_valid():
            audit_events = AuditEvent.objects.filter(
                target_type="Document", target_id=str(pk)
            ).order_by("occurred_at")
            return render(request, self.template_name, {
                "document": document,
                "audit_events": audit_events,
                "void_form": void_form,
            })

        void_document(str(pk), request.user, void_form.cleaned_data["reason"])
        messages.success(request, "Document has been voided. The PDF file is retained for compliance.")
        return redirect("documents:detail", pk=pk)

    def _handle_lock(self, request, document):
        if not request.user.can_lock_document():
            raise PermissionDenied

        reason = request.POST.get("lock_reason", "").strip()
        if len(reason) < 10:
            messages.error(request, "Lock reason must be at least 10 characters.")
            return redirect("documents:detail", pk=document.id)

        lock_document(str(document.id), request.user, reason)
        messages.success(request, "Document locked. Downloads and voids are now blocked.")
        return redirect("documents:detail", pk=document.id)

    def _handle_unlock(self, request, document):
        if not request.user.can_lock_document():
            raise PermissionDenied

        reason = request.POST.get("unlock_reason", "").strip()
        if not reason:
            messages.error(request, "A reason is required to unlock a document.")
            return redirect("documents:detail", pk=document.id)

        unlock_document(str(document.id), request.user, reason)
        messages.success(request, "Document unlocked. Normal access restored.")
        return redirect("documents:detail", pk=document.id)


@login_required
def document_download(request, pk):
    """Re-download a previously generated document."""
    document = get_object_or_404(Document, id=pk)
    _assert_document_access(request, document)

    # Viewers cannot download PDFs
    if request.user.role == User.ROLE_VIEWER:
        raise PermissionDenied

    # Locked documents block all downloads (Finance Head can still download — they own the lock)
    if document.is_locked and not request.user.can_lock_document():
        messages.error(request, "This document is locked and cannot be downloaded.")
        return redirect("documents:detail", pk=pk)

    try:
        pdf_bytes = download_document(str(pk), request.user)
    except Exception as exc:
        messages.error(request, f"Download failed: {exc}")
        return redirect("documents:detail", pk=pk)

    employee_name = document.recipient.name.replace(" ", "_")
    tmpl_name = document.template.name.replace(" ", "_")
    date_str = document.generated_at.strftime("%Y%m%d")
    filename = f"{tmpl_name}_{employee_name}_{date_str}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLogView(LoginRequiredMixin, View):
    """
    CMS audit log — Documents + Other Documents events only (excludes Contract Lens).
    Finance Head and Viewer only.
    """
    template_name = "documents/audit.html"

    def get(self, request):
        if request.user.role not in (User.ROLE_FINANCE_HEAD, User.ROLE_VIEWER):
            raise PermissionDenied

        qs = (
            AuditEvent.objects
            .filter(
                Q(event_type__startswith="document.") |
                Q(event_type__startswith="upload.") |
                Q(event_type__startswith="template.")
            )
            .select_related("actor")
            .order_by("-occurred_at")
        )

        # Filters
        event_type_filter = request.GET.get("event_type", "").strip()
        if event_type_filter:
            qs = qs.filter(event_type=event_type_filter)

        actor_filter = request.GET.get("actor", "").strip()
        if actor_filter:
            qs = qs.filter(
                Q(actor__username__icontains=actor_filter) |
                Q(actor__first_name__icontains=actor_filter) |
                Q(actor__last_name__icontains=actor_filter)
            )

        date_from = request.GET.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)

        date_to = request.GET.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(request.GET.get("page"))

        cms_event_types = [
            (v, l) for v, l in AuditEvent.EVENT_TYPES
            if not v.startswith("contractlens.")
        ]

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "event_types": cms_event_types,
            "event_type_filter": event_type_filter,
            "actor_filter": actor_filter,
            "date_from": date_from,
            "date_to": date_to,
        })


class ContractLensAuditLogView(LoginRequiredMixin, View):
    """
    Contract Lens audit log — contractlens.* events only.
    Finance Head and Viewer only.
    """
    template_name = "documents/contractlens_audit.html"

    def get(self, request):
        if request.user.role not in (User.ROLE_FINANCE_HEAD, User.ROLE_VIEWER):
            raise PermissionDenied

        qs = (
            AuditEvent.objects
            .filter(event_type__startswith="contractlens.")
            .select_related("actor")
            .order_by("-occurred_at")
        )

        event_type_filter = request.GET.get("event_type", "").strip()
        if event_type_filter:
            qs = qs.filter(event_type=event_type_filter)

        actor_filter = request.GET.get("actor", "").strip()
        if actor_filter:
            qs = qs.filter(
                Q(actor__username__icontains=actor_filter) |
                Q(actor__first_name__icontains=actor_filter) |
                Q(actor__last_name__icontains=actor_filter)
            )

        date_from = request.GET.get("date_from", "").strip()
        if date_from:
            qs = qs.filter(occurred_at__date__gte=date_from)

        date_to = request.GET.get("date_to", "").strip()
        if date_to:
            qs = qs.filter(occurred_at__date__lte=date_to)

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(request.GET.get("page"))

        cl_event_types = [
            (v, l) for v, l in AuditEvent.EVENT_TYPES
            if v.startswith("contractlens.")
        ]

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "event_types": cl_event_types,
            "event_type_filter": event_type_filter,
            "actor_filter": actor_filter,
            "date_from": date_from,
            "date_to": date_to,
        })


# ── Contract Lens ──────────────────────────────────────────────────────────────

@login_required
def cadient_talent_view(request):
    if request.user.role not in ("finance_head", "finance_executive"):
        raise PermissionDenied
    return render(request, "contractlens/cadient_talent_app.html")


def _anthropic_client():
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _parse_json_response(text):
    raw = re.sub(r"```json|```", "", text).strip()
    return json.loads(raw)


def _save_cl_files(record_id, files):
    """
    Persist base64-encoded files to encrypted storage.
    Returns a list of {name, type, s3_key, mime_type} for source_files_meta.
    files: list of {name, type, content_b64, mime_type}
    """
    from datetime import datetime
    meta = []
    now = datetime.utcnow()
    for f in files:
        content_b64 = f.get("content_b64", "")
        if not content_b64:
            continue
        raw_bytes = base64.b64decode(content_b64)
        safe_name = re.sub(r"[^\w.\-]", "_", f.get("name", "file"))
        s3_key = f"contractlens/cadient/{now.year}/{now.month:02d}/{record_id}/{safe_name}"
        save_document(s3_key, raw_bytes)
        meta.append({
            "name": f.get("name", ""),
            "type": f.get("type", "other"),
            "s3_key": s3_key,
            "mime_type": f.get("mime_type", "application/octet-stream"),
        })
    return meta


@login_required
@require_POST
def cadient_talent_extract(request):
    try:
        data = json.loads(request.body)
        pdf_b64 = data.get("pdf_b64", "")
        override_name = data.get("override_name", "").strip()
        if not pdf_b64:
            return JsonResponse({"error": "No PDF data provided"}, status=400)

        client = _anthropic_client()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            'Extract contract fields and return ONLY valid JSON, no markdown:\n'
                            '{"customer_name":"","contract_number":null,"start_date":null,'
                            '"end_date":null,"notice_period_days":null,"renewal_type":null,'
                            '"contract_value":null,"payment_terms":null,"governing_law":null,"notes":null}'
                        ),
                    },
                ],
            }],
        )
        result = _parse_json_response(msg.content[0].text)
        if override_name:
            result["customer_name"] = override_name

        # Persist record + file (encrypted)
        record = ContractLensRecord.objects.create(
            customer_name=result.get("customer_name", ""),
            record_type=ContractLensRecord.RECORD_EXTRACT,
            is_group=False,
            contract_data=result,
            created_by=request.user,
        )
        files_meta = _save_cl_files(str(record.id), [{"name": data.get("source_file_name", "contract.pdf"), "type": "contract", "content_b64": pdf_b64, "mime_type": "application/pdf"}])
        record.source_files_meta = files_meta
        record.save()

        # Audit log
        AuditEvent.objects.create(
            event_type="contractlens.extracted",
            actor=request.user,
            target_type="ContractLensRecord",
            target_id=str(record.id),
            metadata={
                "customer_name": result.get("customer_name", ""),
                "record_id": str(record.id),
                "files_stored": len(files_meta),
            },
        )

        result["_server_record_id"] = str(record.id)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def cadient_talent_confirm(request):
    try:
        from datetime import datetime as _dt
        data = json.loads(request.body)
        record_id = data.get("record_id", "").strip()
        if not record_id:
            return JsonResponse({"error": "record_id required"}, status=400)

        try:
            record = ContractLensRecord.objects.get(id=record_id)
        except ContractLensRecord.DoesNotExist:
            return JsonResponse({"error": "Record not found"}, status=404)

        editable = ["customer_name", "contract_number", "start_date", "end_date",
                    "notice_period_days", "renewal_type", "contract_value",
                    "payment_terms", "governing_law", "notes"]

        updated = dict(record.contract_data)
        for f in editable:
            if f in data:
                val = data[f]
                updated[f] = None if val == "" else val

        confirmed_at = _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        confirmed_by = request.user.get_full_name() or request.user.username
        updated["confirmed"] = True
        updated["confirmed_at"] = confirmed_at
        updated["confirmed_by"] = confirmed_by

        record.customer_name = updated.get("customer_name") or record.customer_name
        record.contract_data = updated
        record.save()

        AuditEvent.objects.create(
            event_type="contractlens.confirmed",
            actor=request.user,
            target_type="ContractLensRecord",
            target_id=str(record.id),
            metadata={
                "customer_name": record.customer_name,
                "record_id": str(record.id),
                "confirmed_by": confirmed_by,
                "confirmed_by_id": str(request.user.id),
                "confirmed_at": confirmed_at,
            },
        )

        return JsonResponse({"ok": True, "confirmed_by": confirmed_by, "confirmed_at": confirmed_at})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def cadient_talent_download_file(request, record_id):
    from django.http import Http404
    from documents.services.storage_service import read_document

    try:
        record = ContractLensRecord.objects.get(id=record_id)
    except ContractLensRecord.DoesNotExist:
        raise Http404

    user = request.user
    is_creator = record.created_by_id == user.id
    is_privileged = getattr(user, "role", "") in ("finance_head", "admin")
    if not (is_creator or is_privileged):
        raise PermissionDenied

    files_meta = record.source_files_meta or []
    if not files_meta:
        raise Http404

    # Match by name if provided, else use first file
    requested_name = request.GET.get("name", "").strip()
    if requested_name:
        meta = next((f for f in files_meta if f.get("name") == requested_name), None)
        if not meta:
            raise Http404
    else:
        meta = files_meta[0]

    s3_key = meta.get("s3_key", "")
    if not s3_key:
        raise Http404

    try:
        file_bytes = read_document(s3_key)
    except Exception:
        raise Http404

    fname = meta.get("name", "contract.pdf")
    mime = meta.get("mime_type", "application/octet-stream")
    inline = request.GET.get("inline", "0") == "1"

    AuditEvent.objects.create(
        event_type="contractlens.downloaded",
        actor=user,
        target_type="ContractLensRecord",
        target_id=str(record.id),
        metadata={
            "file": fname,
            "record_id": str(record.id),
            "customer_name": record.customer_name,
            "inline": inline,
        },
    )

    disposition = "inline" if inline else f'attachment; filename="{fname}"'
    response = HttpResponse(file_bytes, content_type=mime)
    response["Content-Disposition"] = disposition
    return response


@login_required
@require_POST
def cadient_talent_analyse_group(request):
    try:
        data = json.loads(request.body)
        name = data.get("name", "")
        note = data.get("note", "")
        files = data.get("files", [])

        if not name:
            return JsonResponse({"error": "Customer name required"}, status=400)
        if not files:
            return JsonResponse({"error": "No files provided"}, status=400)

        DTYPE = {"contract": "Contract", "email": "Email", "amendment": "Amendment", "other": "Other"}
        blocks = []
        fdesc = []

        for f in files:
            fname = f.get("name", "")
            ftype = f.get("type", "other")
            content_b64 = f.get("content_b64", "")
            mime_type = f.get("mime_type", "application/pdf")
            label = DTYPE.get(ftype, ftype)
            fdesc.append(f"[{label}] {fname}")

            if mime_type == "application/pdf":
                blocks.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": content_b64},
                    "title": f"[{label}] {fname}",
                })
            elif mime_type.startswith("image/"):
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": content_b64}})
                blocks.append({"type": "text", "text": f"[Above image: {label} — {fname}]"})
            else:
                text_content = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                blocks.append({"type": "text", "text": f"=== [{label}: {fname}] ===\n{text_content}\n=== END ==="})

        context_line = f"Context: {note}" if note else ""
        blocks.append({
            "type": "text",
            "text": (
                f'Analyse ALL documents together for customer "{name}".\n'
                f'Documents: {", ".join(fdesc)}\n'
                f'{context_line}\n\n'
                'Return ONLY valid JSON, no markdown:\n'
                f'{{"customer_name":"{name}","contract_number":null,"start_date":null,'
                '"end_date":null,"notice_period_days":null,"renewal_type":null,'
                '"contract_value":null,"payment_terms":null,"governing_law":null,'
                '"renewal_confirmed":false,"notes":"2-3 sentence summary of combined document analysis and current contract status"}}'
            ),
        })

        client = _anthropic_client()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1400,
            messages=[{"role": "user", "content": blocks}],
        )
        result = _parse_json_response(msg.content[0].text)

        # Persist record + all files (encrypted)
        record = ContractLensRecord.objects.create(
            customer_name=result.get("customer_name", name),
            record_type=ContractLensRecord.RECORD_GROUP,
            is_group=True,
            contract_data={**result, "context_note": note},
            created_by=request.user,
        )
        files_meta = _save_cl_files(str(record.id), files)
        record.source_files_meta = files_meta
        record.save()

        # Audit log
        AuditEvent.objects.create(
            event_type="contractlens.group_analysed",
            actor=request.user,
            target_type="ContractLensRecord",
            target_id=str(record.id),
            metadata={
                "customer_name": result.get("customer_name", name),
                "record_id": str(record.id),
                "files_stored": len(files_meta),
                "file_types": [f.get("type") for f in files],
            },
        )

        result["_server_record_id"] = str(record.id)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def cadient_talent_merge(request):
    try:
        data = json.loads(request.body)
        name = data.get("name", "")
        contracts_in = data.get("contracts", [])

        if not name:
            return JsonResponse({"error": "Group name required"}, status=400)
        if len(contracts_in) < 2:
            return JsonResponse({"error": "Need at least 2 contracts to merge"}, status=400)

        blocks = []
        fdesc = []

        for c in contracts_in:
            label = c.get("source_label", "Contract")
            src = c.get("source_file", c.get("customer_name", ""))
            fdesc.append(f"[{label}] {src}")

            for f in c.get("files", []):
                content_b64 = f.get("content_b64", "")
                mime_type = f.get("mime_type", "application/pdf")
                fname = f.get("name", "")
                if mime_type == "application/pdf" and content_b64:
                    blocks.append({
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": content_b64},
                        "title": f"Contract: {fname}",
                    })

            extracted = c.get("extracted_data", {})
            blocks.append({
                "type": "text",
                "text": (
                    f'=== Previously extracted data for "{c.get("customer_name", "")}" ===\n'
                    f'{json.dumps(extracted, indent=2)}\n=== END ==='
                ),
            })

        blocks.append({
            "type": "text",
            "text": (
                f'These documents all belong to the same customer: "{name}".\n'
                "Analyse them together as one complete contract record.\n"
                "Return ONLY valid JSON, no markdown:\n"
                f'{{"customer_name":"{name}","contract_number":null,"start_date":null,'
                '"end_date":null,"notice_period_days":null,"renewal_type":null,'
                '"contract_value":null,"payment_terms":null,"governing_law":null,'
                '"renewal_confirmed":false,"notes":"Summary of the combined contract status based on all provided documents"}}'
            ),
        })

        client = _anthropic_client()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1400,
            messages=[{"role": "user", "content": blocks}],
        )
        result = _parse_json_response(msg.content[0].text)

        # Collect all files from all input contracts for encrypted storage
        all_files = [f for c in contracts_in for f in c.get("files", [])]
        record = ContractLensRecord.objects.create(
            customer_name=name,
            record_type=ContractLensRecord.RECORD_MERGE,
            is_group=True,
            contract_data={
                **result,
                "merged_from": [c.get("customer_name", "") for c in contracts_in],
            },
            created_by=request.user,
        )
        files_meta = _save_cl_files(str(record.id), all_files)
        record.source_files_meta = files_meta
        record.save()

        # Audit log
        AuditEvent.objects.create(
            event_type="contractlens.merged",
            actor=request.user,
            target_type="ContractLensRecord",
            target_id=str(record.id),
            metadata={
                "customer_name": name,
                "record_id": str(record.id),
                "merged_from": [c.get("customer_name", "") for c in contracts_in],
                "contracts_merged": len(contracts_in),
                "files_stored": len(files_meta),
            },
        )

        result["_server_record_id"] = str(record.id)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
