from django.contrib import admin
from django.urls import path, include, re_path
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render


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

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("documents/", include("documents.urls", namespace="documents")),
    path("uploads/", include("uploads.urls", namespace="uploads")),
    path("", lambda request: redirect("documents:list"), name="home"),
    # Catch-all — must be last. Renders custom 404 for any unmatched path.
    re_path(r"^.*$", lambda request, *a, **kw: custom_404(request)),
]
