from django.shortcuts import redirect

# URL prefixes that are CMS-only
_CMS_PREFIXES = ('/documents/', '/uploads/', '/contract-lens/')


class RoleBasedAccessMiddleware:
    """Redirect AMS-only roles (employee, manager) away from CMS URLs unless they have explicit access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and request.user.is_ams_only
            and any(request.path.startswith(p) for p in _CMS_PREFIXES)
            and not request.user.has_any_cms_access
            and not request.user.perm_contract_lens
            and not request.user.has_viewer_access
        ):
            return redirect('ams_approvals:inbox')
        return self.get_response(request)
