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

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_FINANCE_HEAD, "Finance Head"),
        (ROLE_FINANCE_EXECUTIVE, "Finance Executive"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_EMPLOYEE, "Employee"),
        (ROLE_VIEWER, "Viewer"),
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

    # Roles that have AMS access only — no CMS access
    AMS_ONLY_ROLES = {ROLE_EMPLOYEE, ROLE_MANAGER}

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
        return self.has_permission('generate_letters')

    def can_manage_templates(self):
        return self.role == self.ROLE_ADMIN

    def can_view_audit_log(self):
        return self.role == self.ROLE_FINANCE_HEAD

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

    # ------------------------------------------------- per-user permission overrides
    _ROLE_PERMISSION_DEFAULTS = {
        'finance_head':      dict(view_documents=True,  generate_letters=True,  download_pdfs=True,  file_uploads=True,  submit_requests=True,  approve_requests=False, view_all_requests=True,  contract_lens=True),
        'finance_executive': dict(view_documents=True,  generate_letters=True,  download_pdfs=True,  file_uploads=True,  submit_requests=True,  approve_requests=True,  view_all_requests=False, contract_lens=True),
        'manager':           dict(view_documents=False, generate_letters=False, download_pdfs=False, file_uploads=False, submit_requests=True,  approve_requests=True,  view_all_requests=False, contract_lens=False),
        'employee':          dict(view_documents=False, generate_letters=False, download_pdfs=False, file_uploads=False, submit_requests=True,  approve_requests=False, view_all_requests=False, contract_lens=False),
        'viewer':            dict(view_documents=True,  generate_letters=False, download_pdfs=False, file_uploads=False, submit_requests=False, approve_requests=False, view_all_requests=False, contract_lens=False),
        'admin':             dict(view_documents=False, generate_letters=False, download_pdfs=False, file_uploads=False, submit_requests=False, approve_requests=False, view_all_requests=False, contract_lens=False),
    }

    def has_permission(self, perm_name):
        """Return True/False for a named permission, respecting per-user overrides."""
        try:
            override = self.permission_overrides.get(permission=perm_name)
            if override.state == UserPermission.STATE_ALLOW:
                return True
            if override.state == UserPermission.STATE_DENY:
                return False
        except UserPermission.DoesNotExist:
            pass
        return self._ROLE_PERMISSION_DEFAULTS.get(self.role, {}).get(perm_name, False)

    # Template-friendly properties (templates cannot call methods with arguments)
    @property
    def perm_view_documents(self):
        return self.has_permission('view_documents')

    @property
    def perm_generate_letters(self):
        return self.has_permission('generate_letters')

    @property
    def perm_download_pdfs(self):
        return self.has_permission('download_pdfs')

    @property
    def perm_file_uploads(self):
        return self.has_permission('file_uploads')

    @property
    def perm_submit_requests(self):
        return self.has_permission('submit_requests')

    @property
    def perm_approve_requests(self):
        return self.has_permission('approve_requests')

    @property
    def perm_view_all_requests(self):
        return self.has_permission('view_all_requests')

    @property
    def perm_contract_lens(self):
        return self.has_permission('contract_lens')

    @property
    def has_any_cms_access(self):
        """True if user can access at least one CMS feature — used to show CMS sidebar."""
        return self.perm_view_documents or self.perm_file_uploads or self.perm_generate_letters


class UserPermission(models.Model):
    PERM_VIEW_DOCUMENTS   = 'view_documents'
    PERM_GENERATE_LETTERS = 'generate_letters'
    PERM_DOWNLOAD_PDFS    = 'download_pdfs'
    PERM_FILE_UPLOADS     = 'file_uploads'
    PERM_SUBMIT_REQUESTS  = 'submit_requests'
    PERM_APPROVE_REQUESTS = 'approve_requests'
    PERM_VIEW_ALL_REQUESTS = 'view_all_requests'
    PERM_CONTRACT_LENS    = 'contract_lens'

    ALL_PERMISSIONS = [
        (PERM_VIEW_DOCUMENTS,    'View Documents'),
        (PERM_GENERATE_LETTERS,  'Generate Letters'),
        (PERM_DOWNLOAD_PDFS,     'Download PDFs'),
        (PERM_FILE_UPLOADS,      'File Uploads'),
        (PERM_SUBMIT_REQUESTS,   'Submit Requests'),
        (PERM_APPROVE_REQUESTS,  'Approve Requests'),
        (PERM_VIEW_ALL_REQUESTS, 'View All Requests'),
        (PERM_CONTRACT_LENS,     'Contract Lens'),
    ]

    STATE_DEFAULT = 'default'
    STATE_ALLOW   = 'allow'
    STATE_DENY    = 'deny'
    STATE_CHOICES = [
        (STATE_DEFAULT, 'Default'),
        (STATE_ALLOW,   'Allow'),
        (STATE_DENY,    'Deny'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='permission_overrides')
    permission = models.CharField(max_length=30, choices=ALL_PERMISSIONS)
    state      = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_DEFAULT)

    class Meta:
        unique_together = ('user', 'permission')
        verbose_name = 'User Permission Override'
