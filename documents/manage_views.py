"""
Finance Head management panel — custom CRUD for users, companies, and templates.
All views require the finance_head role. Django admin is disabled.
"""
import io
from functools import wraps

import mammoth
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from documents.models import AuditEvent, Company, LetterTemplate
from documents.manage_forms import (
    CompanyForm,
    LetterTemplateCreateForm,
    UserCreateForm,
    UserEditForm,
)


def finance_head_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not request.user.is_finance_head_role:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@finance_head_required
def manage_dashboard(request):
    return render(request, "manage/dashboard.html", {
        "user_count": User.objects.count(),
        "active_user_count": User.objects.filter(is_active=True).count(),
        "company_count": Company.objects.count(),
        "active_company_count": Company.objects.filter(is_active=True).count(),
        "template_count": LetterTemplate.objects.filter(is_active=True).count(),
        "total_template_count": LetterTemplate.objects.count(),
    })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@finance_head_required
def manage_users(request):
    users = User.objects.all().order_by("role", "username")
    return render(request, "manage/users.html", {"users": users})


@finance_head_required
def manage_user_add(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            AuditEvent.objects.create(
                event_type="user.created",
                actor=request.user,
                target_type="User",
                target_id=str(user.id),
                metadata={"role": user.role, "username": user.username},
            )
            messages.success(request, f"User \"{user.username}\" created successfully.")
            return redirect("documents:manage_users")
    else:
        form = UserCreateForm()
    return render(request, "manage/user_form.html", {"form": form, "action": "Add User"})


@finance_head_required
def manage_user_edit(request, user_id):
    target = get_object_or_404(User, id=user_id)
    old_role = target.role
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target)
        if form.is_valid():
            user = form.save()
            if old_role != user.role:
                AuditEvent.objects.create(
                    event_type="user.role_changed",
                    actor=request.user,
                    target_type="User",
                    target_id=str(user.id),
                    metadata={"action": "role_changed", "from": old_role, "to": user.role, "username": user.username},
                )
            messages.success(request, f"User \"{user.username}\" updated.")
            return redirect("documents:manage_users")
    else:
        form = UserEditForm(instance=target)
    return render(request, "manage/user_form.html", {
        "form": form,
        "action": "Edit User",
        "target": target,
    })


@finance_head_required
def manage_user_deactivate(request, user_id):
    """Deactivate (soft-delete) a user. Hard deletion is unsafe due to FK references."""
    if request.method != "POST":
        return redirect("documents:manage_users")
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("documents:manage_users")
    target.is_active = False
    target.save(update_fields=["is_active"])
    AuditEvent.objects.create(
        event_type="user.deactivated",
        actor=request.user,
        target_type="User",
        target_id=str(target.id),
        metadata={"username": target.username, "role": target.role},
    )
    messages.success(request, f"User \"{target.username}\" has been deactivated.")
    return redirect("documents:manage_users")


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@finance_head_required
def manage_companies(request):
    companies = Company.objects.all().order_by("name")
    return render(request, "manage/companies.html", {"companies": companies})


@finance_head_required
def manage_company_add(request):
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            company = form.save()
            AuditEvent.objects.create(
                event_type="company.created",
                actor=request.user,
                target_type="Company",
                target_id=str(company.id),
                metadata={"name": company.name},
            )
            messages.success(request, f"Company \"{company.name}\" created.")
            return redirect("documents:manage_companies")
    else:
        form = CompanyForm()
    return render(request, "manage/company_form.html", {"form": form, "action": "Add Company"})


@finance_head_required
def manage_company_edit(request, company_id):
    company = get_object_or_404(Company, id=company_id)
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            company = form.save()
            AuditEvent.objects.create(
                event_type="company.updated",
                actor=request.user,
                target_type="Company",
                target_id=str(company.id),
                metadata={"name": company.name},
            )
            messages.success(request, f"Company \"{company.name}\" updated.")
            return redirect("documents:manage_companies")
    else:
        form = CompanyForm(instance=company)
    return render(request, "manage/company_form.html", {
        "form": form,
        "action": "Edit Company",
        "company": company,
    })


# ---------------------------------------------------------------------------
# Letter Templates
# ---------------------------------------------------------------------------

@finance_head_required
def manage_templates(request):
    templates = LetterTemplate.objects.select_related("created_by").order_by("name", "-version")
    return render(request, "manage/templates.html", {"templates": templates})


_COMPANY_VARS = [
    ("company.name", "Company name"),
    ("company.registered_address", "Registered address"),
    ("company.cin", "CIN number"),
    ("company.gstin", "GSTIN"),
    ("company.signatory_name", "Signatory name"),
    ("company.signatory_designation", "Signatory designation"),
]

_EMPLOYEE_VARS = [
    ("employee.name", "Full name"),
    ("employee.employee_code", "Employee code"),
    ("employee.email", "Email address"),
    ("employee.designation", "Designation"),
    ("employee.department", "Department"),
    ("employee.joining_date", "Joining date"),
]

_DOC_VARS = [
    ("issue_date", "Issue date"),
    ("ref_number", "Reference number"),
    ("variables.field_name", "Any extra field"),
]


@finance_head_required
def manage_template_add(request):
    if request.method == "POST":
        form = LetterTemplateCreateForm(request.POST)
        if form.is_valid():
            tmpl = form.save(commit=False)
            tmpl.created_by = request.user
            tmpl.save()
            if tmpl.is_active:
                tmpl.activate()
                AuditEvent.objects.create(
                    event_type="template.published",
                    actor=request.user,
                    target_type="LetterTemplate",
                    target_id=str(tmpl.id),
                    metadata={"template_name": tmpl.name, "version": tmpl.version},
                )
            messages.success(request, f"Template \"{tmpl}\" created.")
            return redirect("documents:manage_templates")
    else:
        form = LetterTemplateCreateForm(initial={"extra_variables_schema": {}})
    existing_names = list(
        LetterTemplate.objects.values_list("name", flat=True).distinct().order_by("name")
    )
    return render(request, "manage/template_form.html", {
        "form": form,
        "company_vars": _COMPANY_VARS,
        "employee_vars": _EMPLOYEE_VARS,
        "doc_vars": _DOC_VARS,
        "existing_names": existing_names,
    })


@finance_head_required
def manage_template_edit(request, template_id):
    tmpl = get_object_or_404(LetterTemplate, id=template_id)
    if request.method == "POST":
        form = LetterTemplateCreateForm(request.POST, instance=tmpl)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.save()
            if updated.is_active:
                updated.activate()
            AuditEvent.objects.create(
                event_type="template.published",
                actor=request.user,
                target_type="LetterTemplate",
                target_id=str(updated.id),
                metadata={"template_name": updated.name, "version": updated.version, "action": "edited"},
            )
            messages.success(request, f'Template "{updated}" updated.')
            return redirect("documents:manage_templates")
    else:
        form = LetterTemplateCreateForm(instance=tmpl)
    existing_names = list(
        LetterTemplate.objects.values_list("name", flat=True).distinct().order_by("name")
    )
    return render(request, "manage/template_form.html", {
        "form": form,
        "action": f"Edit Template — {tmpl.name} v{tmpl.version}",
        "template": tmpl,
        "company_vars": _COMPANY_VARS,
        "employee_vars": _EMPLOYEE_VARS,
        "doc_vars": _DOC_VARS,
        "existing_names": existing_names,
    })


@finance_head_required
def manage_template_delete(request, template_id):
    if request.method != "POST":
        return redirect("documents:manage_templates")
    tmpl = get_object_or_404(LetterTemplate, id=template_id)
    doc_count = tmpl.documents.count()
    if doc_count:
        messages.error(
            request,
            f'Cannot delete "{tmpl}" — {doc_count} generated document(s) are linked to it.'
        )
        return redirect("documents:manage_templates")
    name = str(tmpl)
    AuditEvent.objects.create(
        event_type="template.deleted",
        actor=request.user,
        target_type="LetterTemplate",
        target_id=str(tmpl.id),
        metadata={"template_name": tmpl.name, "version": tmpl.version},
    )
    tmpl.delete()
    messages.success(request, f'Template "{name}" deleted.')
    return redirect("documents:manage_templates")


@finance_head_required
def manage_template_activate(request, template_id):
    if request.method != "POST":
        return redirect("documents:manage_templates")
    tmpl = get_object_or_404(LetterTemplate, id=template_id)
    tmpl.activate()
    AuditEvent.objects.create(
        event_type="template.published",
        actor=request.user,
        target_type="LetterTemplate",
        target_id=str(tmpl.id),
        metadata={"template_name": tmpl.name, "version": tmpl.version},
    )
    messages.success(request, f"\"{tmpl}\" is now the active version.")
    return redirect("documents:manage_templates")


# ---------------------------------------------------------------------------
# DOCX → HTML conversion (HTMX endpoint)
# ---------------------------------------------------------------------------

# Mammoth style map: strip Word-specific formatting, produce clean semantic HTML
_MAMMOTH_STYLE_MAP = """
p[style-name='Heading 1'] => h2:fresh
p[style-name='Heading 2'] => h3:fresh
p[style-name='Heading 3'] => h4:fresh
r[style-name='Strong'] => strong
"""


@finance_head_required
def manage_template_convert_docx(request):
    """
    JSON endpoint: accepts a .docx POST upload, converts to HTML via mammoth,
    returns {"ok": true, "html": "...", "warnings": [...]} or {"ok": false, "error": "..."}.
    Called by vanilla fetch() in the template — not HTMX (HTMX 1.x file upload is unreliable).
    """
    import json as _json

    if request.method != "POST":
        return HttpResponse(status=405)

    uploaded = request.FILES.get("docx_file")
    if not uploaded:
        return HttpResponse(
            _json.dumps({"ok": False, "error": "No file received."}),
            content_type="application/json", status=400,
        )

    if not uploaded.name.lower().endswith(".docx"):
        return HttpResponse(
            _json.dumps({"ok": False, "error": "Only .docx files are supported."}),
            content_type="application/json", status=400,
        )

    try:
        file_bytes = io.BytesIO(uploaded.read())
        result = mammoth.convert_to_html(
            file_bytes,
            style_map=_MAMMOTH_STYLE_MAP,
            convert_image=mammoth.images.img_element(lambda image: {"src": ""}),
        )
        html = result.value.strip()
        warnings = [str(w.message) for w in result.messages[:5]]
    except Exception as exc:
        return HttpResponse(
            _json.dumps({"ok": False, "error": str(exc)}),
            content_type="application/json", status=500,
        )

    return HttpResponse(
        _json.dumps({"ok": True, "html": html, "warnings": warnings, "filename": uploaded.name}),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Manage Audit Log
# ---------------------------------------------------------------------------

_ROLE_LABELS = {
    "employee":     "Employee",
    "finance_head": "Finance Head",
    "hr":           "HR",
    "admin":        "Admin",
}


def _annotate_manage_event(event):
    """Attach display_* attributes to a manage AuditEvent for simple template rendering."""
    meta = event.metadata or {}

    if event.event_type == "user.created":
        event.src_type      = "user"
        event.badge_label   = "User Created"
        event.badge_cls     = "success"
        event.row_cls       = "ev-success"
        event.display_target = meta.get("username", "—")
        role = _ROLE_LABELS.get(meta.get("role", ""), meta.get("role", ""))
        event.display_details = f"Role: {role}" if role else "—"

    elif event.event_type == "user.role_changed":
        action = meta.get("action", "role_changed")
        event.src_type = "user"
        if action == "deactivated":
            event.badge_label    = "Deactivated"
            event.badge_cls      = "danger"
            event.row_cls        = "ev-danger"
            event.display_target  = meta.get("username", "—")
            event.display_details = "—"
        elif action == "created":
            event.badge_label    = "User Created"
            event.badge_cls      = "success"
            event.row_cls        = "ev-success"
            event.display_target  = meta.get("username", "—")
            role = _ROLE_LABELS.get(meta.get("role", ""), meta.get("role", ""))
            event.display_details = f"Role: {role}" if role else "—"
        else:
            event.badge_label    = "Role Changed"
            event.badge_cls      = "warning"
            event.row_cls        = "ev-warning"
            username = meta.get("username") or event.target_id
            event.display_target  = username if username else "—"
            fr = _ROLE_LABELS.get(meta.get("from", ""), meta.get("from", "?"))
            to = _ROLE_LABELS.get(meta.get("to", ""), meta.get("to", "?"))
            event.display_details = f"{fr} → {to}"

    elif event.event_type == "user.deactivated":
        event.src_type        = "user"
        event.badge_label     = "Deactivated"
        event.badge_cls       = "danger"
        event.row_cls         = "ev-danger"
        event.display_target  = meta.get("username", "—")
        role = _ROLE_LABELS.get(meta.get("role", ""), meta.get("role", ""))
        event.display_details = f"Was: {role}" if role else "—"

    elif event.event_type == "template.published":
        event.src_type = "template"
        action = meta.get("action", "")
        if action == "edited":
            event.badge_label = "Template Updated"
            event.badge_cls   = "info"
            event.row_cls     = "ev-info"
        else:
            event.badge_label = "Template Published"
            event.badge_cls   = "success"
            event.row_cls     = "ev-success"
        event.display_target  = meta.get("template_name", "—")
        ver = meta.get("version")
        event.display_details = f"v{ver}" if ver else "—"

    elif event.event_type == "template.deleted":
        event.src_type        = "template"
        event.badge_label     = "Template Deleted"
        event.badge_cls       = "danger"
        event.row_cls         = "ev-danger"
        event.display_target  = meta.get("template_name", "—")
        ver = meta.get("version")
        event.display_details = f"v{ver}" if ver else "—"

    elif event.event_type == "company.created":
        event.src_type        = "company"
        event.badge_label     = "Company Added"
        event.badge_cls       = "success"
        event.row_cls         = "ev-success"
        event.display_target  = meta.get("name", "—")
        event.display_details = "—"

    elif event.event_type == "company.updated":
        event.src_type        = "company"
        event.badge_label     = "Company Updated"
        event.badge_cls       = "info"
        event.row_cls         = "ev-info"
        event.display_target  = meta.get("name", "—")
        event.display_details = "—"

    else:
        event.src_type        = "other"
        event.badge_label     = event.get_event_type_display()
        event.badge_cls       = "info"
        event.row_cls         = "ev-info"
        event.display_target  = f"{event.target_type}#{event.target_id}" if event.target_type else "—"
        event.display_details = "—"


@finance_head_required
def manage_audit_log(request):
    qs = (
        AuditEvent.objects
        .filter(
            Q(event_type__startswith="user.") |
            Q(event_type__startswith="template.") |
            Q(event_type__startswith="company.")
        )
        .select_related("actor")
        .order_by("-occurred_at")
    )

    event_type_filter = request.GET.get("event_type", "").strip()
    actor_filter      = request.GET.get("actor", "").strip()
    date_from         = request.GET.get("date_from", "").strip()
    date_to           = request.GET.get("date_to", "").strip()

    if event_type_filter:
        qs = qs.filter(event_type=event_type_filter)
    if actor_filter:
        qs = qs.filter(
            Q(actor__username__icontains=actor_filter) |
            Q(actor__first_name__icontains=actor_filter) |
            Q(actor__last_name__icontains=actor_filter)
        )
    if date_from:
        qs = qs.filter(occurred_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_at__date__lte=date_to)

    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(request.GET.get("page"))

    for event in page_obj:
        _annotate_manage_event(event)

    manage_event_types = [
        et for et in AuditEvent.EVENT_TYPES
        if et[0].startswith("user.") or et[0].startswith("template.") or et[0].startswith("company.")
    ]

    return render(request, "manage/audit.html", {
        "page_obj":           page_obj,
        "event_types":        manage_event_types,
        "event_type_filter":  event_type_filter,
        "actor_filter":       actor_filter,
        "date_from":          date_from,
        "date_to":            date_to,
    })
