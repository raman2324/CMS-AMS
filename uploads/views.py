import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from documents.models import Company
from .models import UploadedDocument
from .services import create_uploaded_document, read_upload, delete_upload, log_view, log_download, log_delete


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_queryset(user):
    """Return the queryset of UploadedDocuments visible to this user."""
    if user.is_finance_head_role:
        return UploadedDocument.objects.select_related("company", "uploaded_by").all()

    # Issuers see: their own (any confidentiality) + others' non-confidential
    from django.db.models import Q
    return UploadedDocument.objects.select_related("company", "uploaded_by").filter(
        Q(uploaded_by=user) | Q(is_confidential=False)
    )


def _assert_access(user, doc):
    """Raise PermissionDenied if user cannot access this uploaded document."""
    if user.is_finance_head_role:
        return
    if not user.has_permission('file_uploads'):
        raise PermissionDenied
    if doc.uploaded_by == user:
        return
    if not doc.is_confidential:
        return
    raise PermissionDenied


def _validate_upload(f):
    """Return (error_string | None) after checking extension and size."""
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in UploadedDocument.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(UploadedDocument.ALLOWED_EXTENSIONS))
        return f"File type '.{ext}' is not allowed. Allowed types: {allowed}."
    max_bytes = UploadedDocument.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if f.size > max_bytes:
        return f"File exceeds the {UploadedDocument.MAX_UPLOAD_SIZE_MB} MB limit."
    return None


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class UploadedDocumentListView(LoginRequiredMixin, View):
    template_name = "uploads/list.html"

    def get(self, request):
        if request.user.is_admin_role and not request.user.perm_file_uploads:
            return redirect("documents:manage_dashboard")
        if not request.user.has_permission('file_uploads'):
            raise PermissionDenied

        qs = _user_queryset(request.user).order_by("-uploaded_at")

        # Filters
        q = request.GET.get("q", "").strip()
        doc_type = request.GET.get("type", "")
        company_id = request.GET.get("company", "")

        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(title__icontains=q) | Q(description__icontains=q) | Q(original_filename__icontains=q)
            )
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        if company_id:
            qs = qs.filter(company_id=company_id)

        paginator = Paginator(qs, 50)
        page_obj = paginator.get_page(request.GET.get("page"))

        return render(request, self.template_name, {
            "page_obj": page_obj,
            "type_choices": UploadedDocument.TYPE_CHOICES,
            "companies": Company.objects.filter(is_active=True).order_by("name"),
            "q": q,
            "selected_type": doc_type,
            "selected_company": company_id,
        })


class UploadDocumentView(LoginRequiredMixin, View):
    template_name = "uploads/upload.html"

    def get(self, request):
        if request.user.is_admin_role and not request.user.perm_file_uploads:
            return redirect("documents:manage_dashboard")
        if not request.user.has_permission('file_uploads'):
            raise PermissionDenied

        return render(request, self.template_name, {
            "type_choices": UploadedDocument.TYPE_CHOICES,
            "companies": Company.objects.filter(is_active=True).order_by("name"),
            "max_size_mb": UploadedDocument.MAX_UPLOAD_SIZE_MB,
        })

    def post(self, request):
        if request.user.is_admin_role and not request.user.perm_file_uploads:
            return redirect("documents:manage_dashboard")
        if not request.user.has_permission('file_uploads'):
            raise PermissionDenied

        f = request.FILES.get("file")
        if not f:
            messages.error(request, "No file was selected.")
            return redirect("uploads:upload")

        error = _validate_upload(f)
        if error:
            messages.error(request, error)
            return redirect("uploads:upload")

        title = request.POST.get("title", "").strip() or f.name
        document_type = request.POST.get("document_type", UploadedDocument.TYPE_OTHER)
        description = request.POST.get("description", "").strip()
        company_id = request.POST.get("company", "")
        is_confidential = request.POST.get("is_confidential") == "on"

        company = None
        if company_id:
            try:
                company = Company.objects.get(pk=company_id)
            except Company.DoesNotExist:
                pass

        content_type = f.content_type or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        file_bytes = f.read()

        try:
            doc = create_uploaded_document(
                file_bytes=file_bytes,
                original_filename=f.name,
                content_type=content_type,
                title=title,
                document_type=document_type,
                description=description,
                company=company,
                is_confidential=is_confidential,
                actor=request.user,
            )
        except Exception as exc:
            messages.error(request, f"Upload failed: {exc}")
            return redirect("uploads:upload")

        messages.success(request, f"'{doc.title}' uploaded successfully.")
        return redirect("uploads:list")


def _not_found(request, reason="The requested document or file no longer exists."):
    return render(request, "404.html", {"reason": reason}, status=404)


class UploadedDocumentDetailView(LoginRequiredMixin, View):
    template_name = "uploads/detail.html"

    def get(self, request, pk):
        if request.user.is_admin_role and not request.user.perm_file_uploads:
            return redirect("documents:manage_dashboard")
        try:
            doc = UploadedDocument.objects.get(pk=pk)
        except UploadedDocument.DoesNotExist:
            return _not_found(request, "This file no longer exists. It may have been deleted after this link was created.")
        _assert_access(request.user, doc)
        log_view(doc, request.user)
        return render(request, self.template_name, {"doc": doc})

    def post(self, request, pk):
        if request.user.is_admin_role and not request.user.perm_file_uploads:
            return redirect("documents:manage_dashboard")
        try:
            doc = UploadedDocument.objects.get(pk=pk)
        except UploadedDocument.DoesNotExist:
            return _not_found(request, "This file no longer exists.")
        _assert_access(request.user, doc)

        action = request.POST.get("action")
        if action == "delete":
            # Only uploader or Finance Head can delete
            if doc.uploaded_by != request.user and not request.user.is_finance_head_role:
                raise PermissionDenied
            storage_key = doc.storage_key
            log_delete(doc, request.user)
            doc.delete()
            delete_upload(storage_key)
            messages.success(request, "Document deleted.")
            return redirect("uploads:list")

        return redirect("uploads:detail", pk=pk)


@login_required
def uploaded_document_download(request, pk):
    if request.user.is_admin_role and not request.user.perm_file_uploads:
        return redirect("documents:manage_dashboard")

    try:
        doc = UploadedDocument.objects.get(pk=pk)
    except UploadedDocument.DoesNotExist:
        return _not_found(request, "This file no longer exists. It may have been deleted.")
    _assert_access(request.user, doc)

    file_bytes = read_upload(doc.storage_key)
    log_download(doc, request.user)

    content_type = doc.content_type or "application/octet-stream"
    response = HttpResponse(file_bytes, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{doc.original_filename}"'
    return response
