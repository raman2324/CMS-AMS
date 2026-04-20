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
import uuid as _uuid_mod
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import User
from documents.forms import GenerateDocumentForm, VoidDocumentForm
from documents.models import (
    AuditEvent, Company, Document, Employee,
    LetterTemplate, BASE_VARIABLES_SCHEMA, TEMPLATE_NAME_CHOICES,
)
from documents.services import (
    build_letter_context, download_document, generate_document,
    lock_document, render_letter_html, unlock_document, void_document,
)


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
    if user.role == User.ROLE_ISSUER and document.generated_by != user:
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
    if request.user.role == User.ROLE_ISSUER and request.user.department:
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
    return render(
        request,
        "documents/partials/template_fields.html",
        {"schema": schema, "template": template},
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
            return redirect("admin:index")

        qs = Document.objects.select_related(
            "template", "recipient", "recipient__company", "generated_by"
        )

        # Finance Head sees everything. Issuers see only their own documents.
        if request.user.role == User.ROLE_ISSUER:
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
        if request.user.role == User.ROLE_ISSUER and document.generated_by != request.user:
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
    tmpl_name = document.template.get_name_display().replace(" ", "_")
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
    Dedicated audit log page — Finance Head and Viewer only.
    Issuers and Admins get 403 (they operate the tool, they don't audit it).
    """
    template_name = "documents/audit.html"

    def get(self, request):
        if request.user.role not in (User.ROLE_FINANCE_HEAD, User.ROLE_VIEWER):
            raise PermissionDenied

        qs = AuditEvent.objects.select_related("actor").order_by("-occurred_at")

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

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "event_types": AuditEvent.EVENT_TYPES,
            "event_type_filter": event_type_filter,
            "actor_filter": actor_filter,
            "date_from": date_from,
            "date_to": date_to,
        })
