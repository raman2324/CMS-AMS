from ams.approvals.models import ApprovalRequest, RequestType
from accounts.models import User


def get_subscriptions_for_user(user):
    """Get all subscriptions visible to this user."""
    finance_or_ops = (User.ROLE_FINANCE_EXECUTIVE, User.ROLE_FINANCE_HEAD, User.ROLE_ADMIN, User.ROLE_IT)
    if user.role in finance_or_ops:
        return ApprovalRequest.objects.filter(
            request_type=RequestType.SUBSCRIPTION
        ).select_related('submitted_by').order_by('-created_at')
    return ApprovalRequest.objects.filter(
        request_type=RequestType.SUBSCRIPTION,
        submitted_by=user,
    ).order_by('-created_at')
