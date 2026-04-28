from django.db import models
from django_fsm import FSMField, transition
from django.conf import settings


class RequestType(models.TextChoices):
    SUBSCRIPTION = 'subscription', 'Subscription'
    MISC_EXPENSE = 'misc_expense', 'Misc Expense'


class RequestCategory(models.TextChoices):
    ONE_OFF = 'one_off', 'One-off'
    RECURRING = 'recurring', 'Recurring'


class BillingPeriod(models.TextChoices):
    MONTHLY = 'monthly', 'Monthly'
    ANNUAL = 'annual', 'Annual'
    ONE_TIME = 'one_time', 'One-Time'


class ExpenseType(models.TextChoices):
    ONE_OFF = 'one_off', 'One-Off'
    RECURRING = 'recurring', 'Recurring'


class AmountType(models.TextChoices):
    FIXED = 'fixed', 'Fixed'
    VARIABLE = 'variable', 'Variable'


# FSM states
STATE_PENDING_MANAGER = 'pending_manager'
STATE_PENDING_FINANCE = 'pending_finance'
STATE_REJECTED_MANAGER = 'rejected_manager'
STATE_REJECTED_FINANCE = 'rejected_finance'
STATE_APPROVED = 'approved'
STATE_PROVISIONING = 'provisioning'
STATE_ACTIVE = 'active'
STATE_ACTIVE_PENDING_RENEWAL = 'active_pending_renewal'
STATE_RENEWING = 'renewing'
STATE_TERMINATED = 'terminated'

ALL_STATES = [
    STATE_PENDING_MANAGER, STATE_PENDING_FINANCE,
    STATE_REJECTED_MANAGER, STATE_REJECTED_FINANCE,
    STATE_APPROVED, STATE_PROVISIONING,
    STATE_ACTIVE, STATE_ACTIVE_PENDING_RENEWAL,
    STATE_RENEWING, STATE_TERMINATED,
]

PENDING_STATES = [STATE_PENDING_MANAGER, STATE_PENDING_FINANCE]
ACTIVE_STATES = [STATE_ACTIVE, STATE_ACTIVE_PENDING_RENEWAL, STATE_RENEWING]

STATE_BADGE_COLORS = {
    STATE_PENDING_MANAGER: 'badge bg-warning text-dark',
    STATE_PENDING_FINANCE: 'badge bg-primary',
    STATE_REJECTED_MANAGER: 'badge bg-danger',
    STATE_REJECTED_FINANCE: 'badge bg-danger',
    STATE_APPROVED: 'badge bg-success',
    STATE_PROVISIONING: 'badge bg-secondary',
    STATE_ACTIVE: 'badge bg-success',
    STATE_ACTIVE_PENDING_RENEWAL: 'badge bg-warning text-dark',
    STATE_RENEWING: 'badge bg-info text-dark',
    STATE_TERMINATED: 'badge bg-dark',
}


class ApprovalRequest(models.Model):
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    request_category = models.CharField(
        max_length=20, choices=RequestCategory.choices, blank=True, default=''
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_requests'
    )
    current_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pending_approvals',
    )
    finance_approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_finance_approvals',
    )
    state = FSMField(default=STATE_PENDING_MANAGER, protected=True)

    # Subscription fields
    service_name = models.CharField(max_length=200, blank=True)
    vendor = models.CharField(max_length=200, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    billing_period = models.CharField(
        max_length=20, choices=BillingPeriod.choices, blank=True
    )
    justification = models.TextField(blank=True)
    expires_on = models.DateField(null=True, blank=True)

    # Misc expense fields
    expense_type = models.CharField(
        max_length=20, choices=ExpenseType.choices, blank=True
    )
    amount_type = models.CharField(
        max_length=20, choices=AmountType.choices, blank=True
    )
    receipt = models.FileField(upload_to='receipts/', null=True, blank=True)

    # Provisioning
    vendor_account_id = models.CharField(max_length=200, blank=True)
    billing_start = models.DateField(null=True, blank=True)

    # Approval tracking
    manager_comment = models.TextField(blank=True)
    finance_comment = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        label = self.get_request_category_display() or self.get_request_type_display()
        return f'{label}: {self.service_name or "expense"} by {self.submitted_by.display_name}'

    @property
    def state_badge_color(self):
        return STATE_BADGE_COLORS.get(self.state, 'bg-gray-100 text-gray-800')

    @property
    def state_display(self):
        return self.state.replace('_', ' ').title()

    @property
    def title(self):
        if self.request_category == RequestCategory.RECURRING or self.request_type == RequestType.SUBSCRIPTION:
            return self.service_name or 'Recurring Request'
        return self.service_name or 'One-off Expense'

    @property
    def status_steps(self):
        """Approval workflow steps with completion status for progress display."""
        DONE, CURRENT, PENDING, REJECTED = 'done', 'current', 'pending', 'rejected'
        s = self.state
        is_sub = self.request_type == RequestType.SUBSCRIPTION

        if is_sub:
            steps = [
                {'label': 'Submitted',  'status': DONE},
                {'label': 'Manager',    'status': PENDING},
                {'label': 'Finance',    'status': PENDING},
                {'label': 'Active',     'status': PENDING},
            ]
            if s == 'pending_manager':
                steps[1]['status'] = CURRENT
            elif s == 'rejected_manager':
                steps[1]['status'] = REJECTED
            elif s == 'pending_finance':
                steps[1]['status'] = DONE;  steps[2]['status'] = CURRENT
            elif s == 'provisioning':
                steps[1]['status'] = DONE;  steps[2]['status'] = DONE;  steps[3]['status'] = CURRENT
            elif s == 'rejected_finance':
                steps[1]['status'] = DONE;  steps[2]['status'] = REJECTED
            elif s in ('active', 'active_pending_renewal', 'renewing', 'terminated', 'approved'):
                steps[1]['status'] = DONE;  steps[2]['status'] = DONE;  steps[3]['status'] = DONE
        else:
            steps = [
                {'label': 'Submitted',  'status': DONE},
                {'label': 'Manager',    'status': PENDING},
                {'label': 'Finance',    'status': PENDING},
                {'label': 'Approved',   'status': PENDING},
            ]
            if s == 'pending_manager':
                steps[1]['status'] = CURRENT
            elif s == 'rejected_manager':
                steps[1]['status'] = REJECTED
            elif s == 'pending_finance':
                steps[1]['status'] = DONE;  steps[2]['status'] = CURRENT
            elif s == 'rejected_finance':
                steps[1]['status'] = DONE;  steps[2]['status'] = REJECTED
            elif s in ('approved', 'terminated'):
                steps[1]['status'] = DONE;  steps[2]['status'] = DONE;  steps[3]['status'] = DONE
        return steps

    # ── FSM Transitions ──────────────────────────────────────────────────────

    @transition(field=state, source=STATE_PENDING_MANAGER, target=STATE_PENDING_FINANCE)
    def manager_approve(self, comment=''):
        self.manager_comment = comment

    @transition(field=state, source=STATE_PENDING_MANAGER, target=STATE_REJECTED_MANAGER)
    def manager_reject(self, reason=''):
        self.rejection_reason = reason

    @transition(
        field=state,
        source=STATE_PENDING_FINANCE,
        target=STATE_ACTIVE,
        conditions=[lambda self: self.request_type == RequestType.SUBSCRIPTION],
    )
    def finance_approve_subscription(self, comment=''):
        self.finance_comment = comment

    @transition(
        field=state,
        source=STATE_PENDING_FINANCE,
        target=STATE_APPROVED,
        conditions=[lambda self: self.request_type == RequestType.MISC_EXPENSE],
    )
    def finance_approve_expense(self, comment=''):
        self.finance_comment = comment

    @transition(field=state, source=STATE_PENDING_FINANCE, target=STATE_REJECTED_FINANCE)
    def finance_reject(self, reason=''):
        self.rejection_reason = reason

    @transition(field=state, source=STATE_ACTIVE, target=STATE_ACTIVE_PENDING_RENEWAL)
    def extend_pending(self):
        pass

    @transition(field=state, source=STATE_ACTIVE_PENDING_RENEWAL, target=STATE_RENEWING)
    def start_renewal(self):
        pass

    @transition(field=state, source=STATE_RENEWING, target=STATE_ACTIVE)
    def renewal_approved(self):
        pass

    @transition(field=state, source=STATE_RENEWING, target=STATE_TERMINATED)
    def renewal_rejected(self, reason=''):
        self.rejection_reason = reason

    @transition(
        field=state,
        source=[
            STATE_ACTIVE, STATE_ACTIVE_PENDING_RENEWAL,
            STATE_RENEWING, STATE_APPROVED,
        ],
        target=STATE_TERMINATED,
    )
    def terminate(self, reason=''):
        self.rejection_reason = reason
