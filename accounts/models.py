import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # ------------------------------------------------------------------ roles
    ROLE_ADMIN = "admin"               # backend/codebase admin only
    ROLE_FINANCE_HEAD = "finance_head" # big admin: CMS + AMS finance queue
    ROLE_FINANCE_EXECUTIVE = "finance_executive"  # was: issuer (CMS) / finance (AMS)
    ROLE_MANAGER = "manager"           # AMS: approves team requests
    ROLE_EMPLOYEE = "employee"         # AMS: submits requests
    ROLE_VIEWER = "viewer"             # read-only audit access (CMS + AMS)
    ROLE_IT = "it"                     # AMS: IT provisioning of subscriptions

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_FINANCE_HEAD, "Finance Head"),
        (ROLE_FINANCE_EXECUTIVE, "Finance Executive"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_EMPLOYEE, "Employee"),
        (ROLE_VIEWER, "Viewer"),
        (ROLE_IT, "IT"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_FINANCE_EXECUTIVE)
    # Finance Executives are scoped to a department — they only see documents for
    # employees in their own department. Leave blank to grant access to all departments.
    department = models.CharField(max_length=100, blank=True)
    # Reserved for future SSO integration (django-allauth)
    sso_provider = models.CharField(max_length=50, blank=True)
    sso_subject = models.CharField(max_length=200, blank=True)

    # ---------------------------------------------------------------- AMS fields
    # Nullable — CMS-only users leave these blank.
    reports_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reports',
    )
    offboarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    # --------------------------------------------------------- role properties
    @property
    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN

    @property
    def is_finance_head_role(self):
        return self.role == self.ROLE_FINANCE_HEAD

    @property
    def is_finance_executive_role(self):
        return self.role == self.ROLE_FINANCE_EXECUTIVE

    @property
    def is_viewer_role(self):
        return self.role == self.ROLE_VIEWER

    @property
    def is_manager_role(self):
        return self.role == self.ROLE_MANAGER

    @property
    def is_employee_role(self):
        return self.role == self.ROLE_EMPLOYEE

    @property
    def is_it_role(self):
        return self.role == self.ROLE_IT

    # Roles that have AMS access only — no CMS access
    AMS_ONLY_ROLES = {ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_IT}

    @property
    def is_ams_only(self):
        return self.role in self.AMS_ONLY_ROLES

    # ------------------------------------------- AMS org-hierarchy helpers
    @property
    def is_c_suite(self):
        """C-suite users have no manager and skip the manager approval step."""
        return self.reports_to is None

    @property
    def display_name(self):
        return self.get_full_name() or self.email

    # ------------------------------------------------- CMS permission helpers
    def can_generate(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD, self.ROLE_FINANCE_EXECUTIVE)

    def can_manage_templates(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD)

    def can_view_audit_log(self):
        return self.role in (self.ROLE_ADMIN, self.ROLE_FINANCE_HEAD, self.ROLE_VIEWER)

    def sees_all_documents(self):
        """Finance Head sees every document; all others are restricted to their own."""
        return self.role == self.ROLE_FINANCE_HEAD

    def can_void_any_document(self):
        """Finance Head can void any document. Finance Executives can only void their own."""
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
