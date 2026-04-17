"""
Django admin customizations for HR Document Platform.

Key design decisions:
  - DocumentAdmin.has_add_permission = False  → Documents only created via app
  - AuditEventAdmin is fully read-only         → Immutable by design
  - LetterTemplateAdmin forces version bump    → Active templates are read-only
  - CSV export action on AuditEventAdmin       → Legal/compliance export
"""
import csv
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils import timezone

from documents.models import Company, Employee, LetterTemplate, Document, AuditEvent


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name", "cin", "signatory_name", "signatory_designation", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "short_name", "cin"]
    prepopulated_fields = {"short_name": ("name",)}


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["name", "employee_code", "company", "designation", "department", "joining_date", "source"]
    list_filter = ["company", "department", "source"]
    search_fields = ["name", "employee_code", "email"]
    readonly_fields = ["created_at", "updated_at"]
    list_select_related = ["company"]


# ---------------------------------------------------------------------------
# LetterTemplate
# ---------------------------------------------------------------------------

@admin.register(LetterTemplate)
class LetterTemplateAdmin(admin.ModelAdmin):
    list_display = ["display_name", "version", "is_active", "created_by", "created_at"]
    list_filter = ["name", "is_active"]
    readonly_fields = ["version", "created_at", "created_by"]
    actions = ["activate_template"]

    def display_name(self, obj):
        badge = (
            '<span class="badge" style="background:#198754;color:#fff;padding:2px 8px;border-radius:4px">Active</span>'
            if obj.is_active else ""
        )
        return format_html("{} v{} {}", obj.get_name_display(), obj.version, badge)
    display_name.short_description = "Template"

    def get_readonly_fields(self, request, obj=None):
        """Active templates are read-only. Edit = create a new version via admin action."""
        base = list(self.readonly_fields)
        if obj and obj.is_active:
            base += ["html_content", "name", "extra_variables_schema"]
        return base

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Activate selected template version (deactivates previous)")
    def activate_template(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one template to activate.", level=messages.WARNING)
            return
        tmpl = queryset.first()
        tmpl.activate()
        AuditEvent.objects.create(
            event_type="template.published",
            actor=request.user,
            target_type="LetterTemplate",
            target_id=str(tmpl.id),
            metadata={"template_name": tmpl.name, "version": tmpl.version},
        )
        self.message_user(request, f"Activated {tmpl}. Previous version deactivated.")


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        "recipient_name", "template_name", "company", "status_badge",
        "generated_by", "generated_at", "hash_short", "download_count",
    ]
    list_filter = ["status", "company", "template__name", "generated_at"]
    search_fields = ["recipient__name", "recipient__employee_code", "content_hash", "id"]
    readonly_fields = [
        "id", "company", "template", "recipient", "variables_snapshot",
        "s3_key", "content_hash", "generated_by", "generated_at",
        "status", "download_count",
    ]
    list_select_related = ["recipient", "template", "company", "generated_by"]
    date_hierarchy = "generated_at"

    def recipient_name(self, obj):
        return obj.recipient.name
    recipient_name.short_description = "Recipient"

    def template_name(self, obj):
        return f"{obj.template.get_name_display()} v{obj.template.version}"
    template_name.short_description = "Template"

    def status_badge(self, obj):
        color = "#dc3545" if obj.is_void else "#198754"
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:0.8em">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def hash_short(self, obj):
        return obj.content_hash[:12] + "…" if obj.content_hash else "—"
    hash_short.short_description = "SHA-256 (12 chars)"

    def has_add_permission(self, request):
        return False  # Documents are only created via the app workflow

    def has_delete_permission(self, request, obj=None):
        return False  # S3 Object Lock — never delete documents


# ---------------------------------------------------------------------------
# AuditEvent  (fully read-only)
# ---------------------------------------------------------------------------

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "actor", "target_type", "target_id", "occurred_at"]
    list_filter = ["event_type", "occurred_at"]
    search_fields = ["actor__username", "target_id", "content_hash"]
    readonly_fields = [
        "id", "event_type", "actor", "target_type", "target_id",
        "metadata", "occurred_at", "content_hash",
    ]
    date_hierarchy = "occurred_at"
    actions = ["export_csv"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Export selected audit events as CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        ts = timezone.now().strftime("%Y%m%d_%H%M%S")
        response["Content-Disposition"] = f'attachment; filename="audit_export_{ts}.csv"'

        writer = csv.writer(response)
        writer.writerow(["id", "event_type", "actor", "target_type", "target_id",
                         "content_hash", "occurred_at", "metadata"])
        for event in queryset.select_related("actor").order_by("occurred_at"):
            writer.writerow([
                str(event.id),
                event.event_type,
                str(event.actor) if event.actor else "",
                event.target_type,
                event.target_id,
                event.content_hash,
                event.occurred_at.isoformat(),
                event.metadata,
            ])
        return response
