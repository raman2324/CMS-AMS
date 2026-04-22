from django.contrib import admin
from .models import UploadedDocument


@admin.register(UploadedDocument)
class UploadedDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title", "document_type", "company", "is_confidential",
        "file_size_display", "uploaded_by", "uploaded_at",
    )
    list_filter = ("document_type", "is_confidential", "company")
    search_fields = ("title", "description", "original_filename", "uploaded_by__username")
    readonly_fields = (
        "id", "storage_key", "original_filename", "file_size",
        "content_type", "uploaded_by", "uploaded_at",
    )
    ordering = ("-uploaded_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
