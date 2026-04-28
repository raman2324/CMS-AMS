import csv
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import AuditLog
from accounts.models import User
from ams.approvals.models import ApprovalRequest

_AUDIT_ROLES = (User.ROLE_FINANCE_HEAD, User.ROLE_ADMIN, User.ROLE_VIEWER)
_OFFBOARD_ROLES = (User.ROLE_FINANCE_HEAD, User.ROLE_ADMIN)


def require_audit_access(user):
    if user.role not in _AUDIT_ROLES:
        raise PermissionDenied('Finance Head, Admin, or Viewer role required.')


@login_required
def audit_log(request):
    require_audit_access(request.user)

    logs = AuditLog.objects.select_related('actor').all()

    # Filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    action_type = request.GET.get('action_type')
    actor_id = request.GET.get('actor_id')

    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)
    if action_type:
        logs = logs.filter(action__icontains=action_type)
    if actor_id:
        logs = logs.filter(actor_id=actor_id)

    logs = logs[:500]

    # Build service name lookup for request-type log entries
    request_ids = [log.target_id for log in logs if log.target_type == 'request']
    service_map = {}
    if request_ids:
        for r in ApprovalRequest.objects.filter(pk__in=request_ids).values('id', 'service_name', 'request_type'):
            service_map[r['id']] = r['service_name'] or (
                'Misc Expense' if r['request_type'] == 'misc_expense' else 'Subscription'
            )

    # Annotate each log with a display-friendly service name
    for log in logs:
        if log.target_type == 'request':
            log.service_name_display = service_map.get(log.target_id, '—')
        else:
            log.service_name_display = f'{log.target_type}#{log.target_id}'

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Actor', 'Service Name', 'Action', 'Target Type', 'Target ID', 'Notes', 'Created At'])
        for log in logs:
            writer.writerow([
                log.id,
                log.actor.email if log.actor else 'system',
                log.service_name_display,
                log.action,
                log.target_type,
                log.target_id,
                log.notes,
                log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            ])
        return response

    actors = User.objects.filter(is_active=True).order_by('email')
    unique_actions = AuditLog.objects.values_list('action', flat=True).distinct().order_by('action')

    return render(request, 'ams/admin_ams/audit.html', {
        'logs': logs,
        'actors': actors,
        'unique_actions': unique_actions,
        'filters': {
            'date_from': date_from or '',
            'date_to': date_to or '',
            'action_type': action_type or '',
            'actor_id': actor_id or '',
        },
    })


@login_required
def my_audit_log(request):
    logs = list(
        AuditLog.objects
        .filter(actor=request.user)
        .select_related('actor')
        .order_by('-created_at')[:200]
    )
    request_ids = [log.target_id for log in logs if log.target_type == 'request']
    service_map = {}
    if request_ids:
        for r in ApprovalRequest.objects.filter(pk__in=request_ids).values('id', 'service_name', 'request_type'):
            service_map[r['id']] = r['service_name'] or (
                'Misc Expense' if r['request_type'] == 'misc_expense' else 'Subscription'
            )
    for log in logs:
        if log.target_type == 'request':
            log.service_name_display = service_map.get(log.target_id, '—')
        else:
            log.service_name_display = f'{log.target_type}#{log.target_id}'
    return render(request, 'ams/admin_ams/my_audit.html', {'logs': logs})


@login_required
def offboard(request):
    if request.user.role not in _OFFBOARD_ROLES:
        raise PermissionDenied('Finance Head or Admin role required.')

    from accounts.services import offboard_employee, get_offboard_preview

    # Finance Head can only offboard non-privileged roles; Admin can offboard anyone
    _offboardable_roles = [
        User.ROLE_EMPLOYEE, User.ROLE_MANAGER,
        User.ROLE_FINANCE_EXECUTIVE, User.ROLE_VIEWER,
    ]
    base_qs = User.objects.filter(is_active=True).exclude(id=request.user.id)
    if request.user.role == User.ROLE_FINANCE_HEAD:
        base_qs = base_qs.filter(role__in=_offboardable_roles)
    active_employees = base_qs.order_by('email')

    result = None
    preview = None
    selected_user = None

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        last_day_str = request.POST.get('last_day', '')

        try:
            selected_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            from django.contrib import messages
            messages.error(request, 'User not found.')
            return redirect('ams_audit:offboard')

        # Server-side guard: Finance Head cannot offboard admins or other finance heads
        if request.user.role == User.ROLE_FINANCE_HEAD and selected_user.role not in _offboardable_roles:
            from django.contrib import messages
            messages.error(request, f'You do not have permission to offboard {selected_user.display_name}.')
            return redirect('ams_audit:offboard')

        if action == 'preview':
            preview = get_offboard_preview(selected_user)
        elif action == 'confirm':
            from datetime import date
            last_day = date.fromisoformat(last_day_str) if last_day_str else date.today()
            result = offboard_employee(selected_user, last_day=last_day, actor=request.user)
            from django.contrib import messages
            if result.get('already_offboarded'):
                messages.warning(request, f'{selected_user.display_name} was already offboarded.')
            else:
                messages.success(
                    request,
                    f'{selected_user.display_name} offboarded. '
                    f'{len(result["terminated"])} subscriptions terminated, '
                    f'{len(result["reassigned"])} approvals reassigned.'
                )
            return redirect('ams_audit:offboard')

    return render(request, 'ams/admin_ams/offboard.html', {
        'active_employees': active_employees,
        'preview': preview,
        'selected_user': selected_user,
        'result': result,
    })
