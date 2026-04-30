from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum

from .models import ApprovalRequest, RequestType, PENDING_STATES
from .services import (
    submit, manager_approve, manager_reject,
    finance_approve, finance_reject,
    initiate_renewal, complete_renewal, terminate_request,
    manager_approve_renewal, manager_reject_renewal,
)
from accounts.models import User
from ams.audit.models import AuditLog


@login_required
def request_new(request):
    """Create a new approval request (one-off or recurring)."""
    if not request.user.has_permission('submit_requests'):
        messages.error(request, "Submitting requests has been restricted for your account. Contact your Finance Head.")
        return redirect('ams_approvals:all_requests')
    if request.method == 'POST':
        from ams.approvals.models import RequestCategory
        request_category = request.POST.get('request_category', '')
        if request_category == RequestCategory.RECURRING:
            req_type = RequestType.SUBSCRIPTION
        elif request_category == RequestCategory.ONE_OFF:
            req_type = RequestType.MISC_EXPENSE
        else:
            messages.error(request, 'Please select One-off or Recurring.')
            return redirect('ams_approvals:request_new')

        try:
            obj = ApprovalRequest(
                request_type=req_type,
                request_category=request_category,
                submitted_by=request.user,
            )

            cost_str = request.POST.get('cost', '').strip()
            try:
                obj.cost = Decimal(cost_str) if cost_str else None
            except InvalidOperation:
                obj.cost = None

            obj.justification = request.POST.get('justification', '').strip()
            if 'receipt' in request.FILES:
                obj.receipt = request.FILES['receipt']

            if request_category == RequestCategory.RECURRING:
                obj.service_name = request.POST.get('service_name', '').strip()
                obj.vendor = request.POST.get('vendor', '').strip()
                obj.billing_period = request.POST.get('billing_period', '')
                obj.amount_type = request.POST.get('amount_type', '')
                expires_on_str = request.POST.get('expires_on', '').strip()
                if expires_on_str:
                    from datetime import date as _d
                    obj.expires_on = _d.fromisoformat(expires_on_str)
            else:  # one_off
                obj.service_name = request.POST.get('service_name_oneoff', '').strip() or request.POST.get('description', '').strip()
                obj.expense_type = RequestCategory.ONE_OFF

            manager_id = request.POST.get('manager_id', '').strip()
            if manager_id:
                try:
                    obj.current_approver = User.objects.get(id=manager_id)
                except User.DoesNotExist:
                    pass

            obj.save()
            obj = submit(obj, actor=request.user)
            messages.success(
                request,
                f'Request #{obj.id} submitted successfully. Current state: {obj.state_display}'
            )
            return redirect('ams_approvals:request_detail', pk=obj.pk)

        except Exception as e:
            messages.error(request, f'Error submitting request: {e}')
            return redirect('ams_approvals:request_new')

    managers = User.objects.filter(role=User.ROLE_MANAGER, is_active=True).exclude(pk=request.user.pk).order_by('first_name')
    return render(request, 'ams/approvals/request_new.html', {
        'managers': managers,
    })


@login_required
def request_detail(request, pk):
    """Show request detail with approval actions."""
    obj = get_object_or_404(ApprovalRequest, pk=pk)

    # Check access: submitter, assigned approver, or anyone with view_all_requests
    user = request.user
    can_view = (
        obj.submitted_by == user or
        obj.current_approver == user or
        user.has_permission('view_all_requests')
    )
    if not can_view:
        messages.error(request, "You don't have permission to view that request.")
        return redirect('ams_approvals:inbox')

    audit_logs = AuditLog.objects.filter(
        target_type='request', target_id=obj.id
    ).select_related('actor').order_by('created_at')

    from datetime import date as _date, timedelta as _timedelta
    _today = _date.today()

    is_approver = (obj.current_approver == user)
    can_manager_approve = (
        is_approver and obj.state in ('pending_manager', 'active_pending_renewal')
    )
    can_finance_approve = (
        is_approver and
        user.has_permission('approve_requests') and
        obj.state in ('pending_finance', 'renewing')
    )
    can_provision = False

    _near_expiry = (
        obj.billing_period in ('monthly', 'annual') and
        obj.expires_on is not None and
        obj.expires_on <= _today + _timedelta(days=10)
    )
    can_renew = (
        obj.state == 'active' and
        obj.request_type == RequestType.SUBSCRIPTION and
        obj.submitted_by == user and
        _near_expiry
    )
    _finance_head_terminable = ('active', 'active_pending_renewal', 'renewing', 'provisioning', 'approved', 'pending_finance')
    _finance_exec_terminable = ('active', 'active_pending_renewal', 'renewing', 'provisioning', 'approved')
    can_terminate = (
        (user.role == User.ROLE_FINANCE_HEAD and obj.state in _finance_head_terminable) or
        (user.role == User.ROLE_FINANCE_EXECUTIVE and obj.state in _finance_exec_terminable)
    )

    finance_users = User.objects.filter(role=User.ROLE_FINANCE_EXECUTIVE, is_active=True).exclude(pk=obj.submitted_by.pk).order_by('first_name')
    managers = list(User.objects.filter(role=User.ROLE_MANAGER, is_active=True).order_by('first_name'))
    managers_json = [
        {'id': str(m.id), 'name': m.display_name}
        for m in managers
    ]

    context = {
        'obj': obj,
        'audit_logs': audit_logs,
        'can_manager_approve': can_manager_approve,
        'can_finance_approve': can_finance_approve,
        'can_provision': can_provision,
        'can_renew': can_renew,
        'can_terminate': can_terminate,
        'finance_users': finance_users,
        'managers': managers,
        'managers_json': managers_json,
        'today': _today,
    }

    if request.htmx:
        return render(request, 'ams/approvals/partials/request_detail_body.html', context)
    return render(request, 'ams/approvals/request_detail.html', context)


@login_required
def action_approve(request, pk):
    """HTMX: approve a request (manager or finance depending on state)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    comment = request.POST.get('comment', '')
    finance_id = request.POST.get('finance_id', '').strip()

    try:
        if obj.state == 'pending_manager':
            obj = manager_approve(obj, actor=request.user, comment=comment,
                                  finance_user_id=finance_id or None)
        elif obj.state == 'pending_finance':
            obj = finance_approve(obj, actor=request.user, comment=comment)
        elif obj.state == 'active_pending_renewal':
            obj = manager_approve_renewal(obj, actor=request.user, comment=comment)
        elif obj.state == 'renewing':
            obj = complete_renewal(obj, actor=request.user, approved=True)
        else:
            raise PermissionDenied('Cannot approve in current state.')

        messages.success(request, f'Request approved. New state: {obj.state_display}')
    except PermissionDenied as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Error: {e}')

    if request.htmx:
        return redirect('ams_approvals:request_detail', pk=pk)
    return redirect('ams_approvals:request_detail', pk=pk)


@login_required
def action_reject(request, pk):
    """HTMX: reject a request."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)
    reason = request.POST.get('reason', '')

    try:
        if obj.state == 'pending_manager':
            obj = manager_reject(obj, actor=request.user, reason=reason)
        elif obj.state == 'pending_finance':
            obj = finance_reject(obj, actor=request.user, reason=reason)
        elif obj.state == 'active_pending_renewal':
            obj = manager_reject_renewal(obj, actor=request.user, reason=reason)
        elif obj.state == 'renewing':
            obj = complete_renewal(obj, actor=request.user, approved=False, reason=reason)
        else:
            raise PermissionDenied('Cannot reject in current state.')

        messages.success(request, f'Request rejected. State: {obj.state_display}')
    except PermissionDenied as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('ams_approvals:request_detail', pk=pk)


@login_required
def action_renew(request, pk):
    """Initiate renewal for an active subscription."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)

    if obj.submitted_by != request.user:
        messages.error(request, "You are not allowed to renew this request.")
        return redirect('ams_approvals:request_detail', pk=pk)

    # Enforce 10-day renewal window for employees
    if request.user.role == User.ROLE_EMPLOYEE and obj.expires_on:
        from django.utils import timezone
        days_until_expiry = (obj.expires_on - timezone.now().date()).days
        if days_until_expiry > 10:
            messages.error(request, "Renewal is only available within 10 days of expiry.")
            return redirect('ams_approvals:request_detail', pk=pk)

    renewal_cost = None
    if obj.amount_type == 'variable':
        cost_str = request.POST.get('renewal_cost', '').strip()
        if not cost_str:
            messages.error(request, 'Renewal cost is required for variable subscriptions.')
            return redirect('ams_approvals:request_detail', pk=pk)
        try:
            renewal_cost = Decimal(cost_str)
        except InvalidOperation:
            messages.error(request, 'Invalid cost value.')
            return redirect('ams_approvals:request_detail', pk=pk)

    manager_id = request.POST.get('manager_id', '').strip() or None

    try:
        obj = initiate_renewal(
            obj, actor=request.user,
            renewal_cost=renewal_cost,
            manager_id=manager_id,
        )
        messages.success(request, f'Renewal submitted. State: {obj.state_display}')
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('ams_approvals:request_detail', pk=pk)


@login_required
def action_terminate(request, pk):
    """Terminate an active subscription."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    obj = get_object_or_404(ApprovalRequest, pk=pk)

    if request.user.role not in (User.ROLE_FINANCE_HEAD, User.ROLE_FINANCE_EXECUTIVE):
        raise PermissionDenied("Only Finance users can terminate subscriptions.")

    reason = request.POST.get('reason', '')

    try:
        obj = terminate_request(obj, actor=request.user, reason=reason)
        messages.success(request, 'Request terminated.')
    except Exception as e:
        messages.error(request, f'Error: {e}')

    return redirect('ams_approvals:request_detail', pk=pk)


@login_required
def inbox(request):
    """Inbox: requests pending action from the current user."""
    user = request.user

    if user.role == User.ROLE_EMPLOYEE:
        return redirect('ams_approvals:all_requests')

    # Requests where I am the current approver — finance roles see pending_finance
    # via finance_queue instead, so exclude it here to avoid duplicates.
    finance_roles = (User.ROLE_FINANCE_EXECUTIVE, User.ROLE_FINANCE_HEAD)
    my_pending_states = (
        ['pending_manager']
        if user.role in finance_roles
        else [*PENDING_STATES, 'active_pending_renewal']
    )
    my_pending = ApprovalRequest.objects.filter(
        current_approver=user,
        state__in=my_pending_states,
    ).select_related('submitted_by', 'current_approver')

    # Finance renewal queue
    renewal_queue = ApprovalRequest.objects.none()
    if user.role in finance_roles:
        renewal_queue = ApprovalRequest.objects.filter(
            state='renewing',
        ).select_related('submitted_by', 'current_approver')

    # Finance pending queue — all pending_finance requests, not just assigned ones
    finance_queue = ApprovalRequest.objects.none()
    if user.role in finance_roles:
        finance_queue = ApprovalRequest.objects.filter(
            state='pending_finance',
        ).select_related('submitted_by', 'current_approver')

    # Upcoming renewals — subscriptions where employee has clicked Renew once
    # but hasn't yet submitted to finance (active_pending_renewal state)
    upcoming_renewals = ApprovalRequest.objects.none()
    if user.role in finance_roles:
        upcoming_renewals = ApprovalRequest.objects.filter(
            state='active_pending_renewal',
            request_type=RequestType.SUBSCRIPTION,
        ).select_related('submitted_by')

    context = {
        'my_pending': my_pending,
        'renewal_queue': renewal_queue,
        'finance_queue': finance_queue,
        'upcoming_renewals': upcoming_renewals,
    }
    return render(request, 'ams/approvals/inbox.html', context)


@login_required
def my_requests(request):
    """Pending requests submitted by current user (both subscriptions and expenses)."""
    IN_PROGRESS = [
        'pending_manager', 'pending_finance', 'provisioning',
        'active_pending_renewal', 'renewing',
    ]
    pending = ApprovalRequest.objects.filter(
        submitted_by=request.user,
        state__in=IN_PROGRESS,
    ).select_related('submitted_by', 'current_approver').order_by('-created_at')

    return render(request, 'ams/approvals/my_requests.html', {
        'pending': pending,
    })


@login_required
def all_requests(request):
    """Unified view of all the user's subscriptions and expenses, grouped by status."""
    if request.user.has_permission('view_all_requests'):
        base_qs = ApprovalRequest.objects.select_related('current_approver').order_by('-created_at')
    else:
        base_qs = ApprovalRequest.objects.filter(
            submitted_by=request.user,
        ).select_related('current_approver').order_by('-created_at')

    active_subs    = base_qs.filter(request_type=RequestType.SUBSCRIPTION, state='active')
    renewing_subs  = base_qs.filter(request_type=RequestType.SUBSCRIPTION, state__in=['active_pending_renewal', 'renewing'])
    pending_all    = base_qs.filter(state__in=['pending_manager', 'pending_finance', 'provisioning'])
    approved_exp   = base_qs.filter(request_type=RequestType.MISC_EXPENSE, state='approved')
    rejected_all   = base_qs.filter(state__in=['rejected_manager', 'rejected_finance'])
    terminated_all = base_qs.filter(state='terminated')
    expired_subs   = base_qs.filter(request_type=RequestType.SUBSCRIPTION, state='expired')

    from datetime import date as _date, timedelta as _td
    _today = _date.today()
    expiring_soon_pks = set(
        active_subs.filter(
            billing_period__in=['monthly', 'annual'],
            expires_on__isnull=False,
            expires_on__lte=_today + _td(days=10),
        ).values_list('pk', flat=True)
    )

    exp_qs = base_qs.filter(request_type=RequestType.MISC_EXPENSE)
    approved_exp_amount  = exp_qs.filter(state='approved').aggregate(t=Sum('cost'))['t'] or 0
    pending_exp_amount   = exp_qs.filter(state__in=['pending_manager', 'pending_finance']).aggregate(t=Sum('cost'))['t'] or 0
    active_subs_cost     = active_subs.aggregate(t=Sum('cost'))['t'] or 0
    total_expense_amount = active_subs_cost + approved_exp_amount

    return render(request, 'ams/approvals/all_requests.html', {
        'active_subs':           active_subs,
        'renewing_subs':         renewing_subs,
        'pending_all':           pending_all,
        'approved_exp':          approved_exp,
        'rejected_all':          rejected_all,
        'terminated_all':        terminated_all,
        'expired_subs':          expired_subs,
        'total_subs':            base_qs.filter(request_type=RequestType.SUBSCRIPTION).count(),
        'pending_exp_amount':    pending_exp_amount,
        'total_expense_amount':  total_expense_amount,
        'expiring_soon_pks':     expiring_soon_pks,
    })
