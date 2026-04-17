"""
Views for the HR Document Generation Platform.

Routes:
  GET  /documents/                  DocumentListView
  GET  /documents/generate/         GenerateDocumentView
  POST /documents/generate/         GenerateDocumentView (generate PDF)
  GET  /documents/<uuid>/           DocumentDetailView
  POST /documents/<uuid>/           DocumentDetailView (void action)
  GET  /documents/<uuid>/download/  document_download

HTMX endpoints (return HTML fragments):
  GET  /documents/api/employees/              employee_search
  GET  /documents/api/template-fields/<uuid>/ template_fields
  POST /documents/api/preview/               preview_letter
"""
import uuid as _uuid_mod
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from documents.forms import GenerateDocumentForm, VoidDocumentForm
from documents.models import (
    AuditEvent, Company, Document, Employee,
    LetterTemplate, BASE_VARIABLES_SCHEMA, TEMPLATE_NAME_CHOICES,
)
from documents.services import (
    build_letter_context, download_document, generate_document,
    render_letter_html, void_document,
)


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
    from accounts.models import User
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

        # Stream PDF as direct download
        employee_name = document.recipient.name.replace(" ", "_")
        tmpl_name = document.template.get_name_display().replace(" ", "_")
        date_str = document.generated_at.strftime("%Y%m%d")
        filename = f"{tmpl_name}_{employee_name}_{date_str}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class DocumentListView(LoginRequiredMixin, View):
    template_name = "documents/list.html"

    def get(self, request):
        from accounts.models import User

        qs = Document.objects.select_related(
            "template", "recipient", "recipient__company", "generated_by"
        )

        # Department scoping for Issuers
        if request.user.role == User.ROLE_ISSUER and request.user.department:
            qs = qs.filter(recipient__department=request.user.department)

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

        return render(request, self.template_name, {
            "documents": qs[:200],
            "search_query": search_query,
            "status_filter": status_filter,
            "template_filter": template_filter,
            "template_choices": TEMPLATE_NAME_CHOICES,
            "status_choices": Document.STATUS_CHOICES,
        })


class DocumentDetailView(LoginRequiredMixin, View):
    template_name = "documents/detail.html"

    def get(self, request, pk):
        document = get_object_or_404(Document, id=pk)
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
        """Void a document."""
        document = get_object_or_404(Document, id=pk)
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


@login_required
def document_download(request, pk):
    """Re-download a previously generated document."""
    document = get_object_or_404(Document, id=pk)

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
