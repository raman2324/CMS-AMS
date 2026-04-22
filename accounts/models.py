import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_FINANCE_HEAD = "finance_head"
    ROLE_ISSUER = "issuer"
    ROLE_VIEWER = "viewer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_FINANCE_HEAD, "Finance Head"),
        (ROLE_ISSUER, "Issuer"),
        (ROLE_VIEWER, "Viewer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ISSUER)
    # Issuers are scoped to a department — they only see documents for employees
    # in their own department. Leave blank to grant access to all departments.
    department = models.CharField(max_length=100, blank=True)
    # Reserved for future SSO integration (django-allauth)
    sso_provider = models.CharField(max_length=50, blank=True)
    sso_subject = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_finance_head_role(self):
        return self.role == self.ROLE_FINANCE_HEAD

    @property
    def is_issuer_role(self):
        return self.role == self.ROLE_ISSUER

    @property
    def is_viewer_role(self):
        return self.role == self.ROLE_VIEWER

    def can_generate(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD, self.ROLE_ISSUER)

    def can_manage_templates(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD)

    def can_view_audit_log(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD, self.ROLE_VIEWER)

    def sees_all_documents(self):
        """Finance Head sees every document; all others are restricted to their own."""
        return self.role == self.ROLE_FINANCE_HEAD

    def can_void_any_document(self):
        """Finance Head can void any document. Issuers can only void their own."""
        return self.role == self.ROLE_FINANCE_HEAD

    def can_lock_document(self):
        """Only Finance Head can lock/unlock documents (legal hold)."""
        return self.role == self.ROLE_FINANCE_HEAD

    # ------------------------------------------------------------------
    # Django permission overrides — Finance Head and Admin get full access
    # to the Django admin panel (equivalent to superuser, without the flag).
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def has_perm(self, perm, obj=None):
        return super().has_perm(perm, obj)

    def has_module_perms(self, app_label):
        return super().has_module_perms(app_label)
