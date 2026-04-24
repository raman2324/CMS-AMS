from django.contrib import admin
from django.http import HttpResponseForbidden
from django.urls import path, include, re_path
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required


def custom_404(request, exception=None, reason=None):
    msg = reason
    if not msg and exception:
        raw = str(getattr(exception, "args", [None])[0] or "")
        if "matches the given query" in raw:
            msg = "The requested document or file no longer exists."
        elif raw:
            msg = raw
    return render(request, "404.html", {"reason": msg}, status=404)


handler404 = custom_404

# Disable Django admin for all users — management is done via /documents/manage/
admin.site.has_permission = lambda request: False

urlpatterns = [
    path("admin/", lambda request, *a, **kw: HttpResponseForbidden(
        "Django admin is disabled. Use the Manage panel instead."
    )),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("documents/", include("documents.urls", namespace="documents")),
    path("uploads/", include("uploads.urls", namespace="uploads")),
    path("ams/", include("ams.urls")),
    path("accounts/", include("allauth.urls")),
    path("", lambda request: (
        redirect("ams_approvals:inbox") if request.user.is_authenticated and request.user.is_ams_only
        else redirect("documents:list")
    ), name="home"),
    # Catch-all — must be last. Renders custom 404 for any unmatched path.
    re_path(r"^.*$", lambda request, *a, **kw: custom_404(request)),
]
