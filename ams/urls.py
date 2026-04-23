from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # allauth account-management (password reset, signup, etc.)
    # Login is intentionally excluded — all users log in at /login/
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("ams.ams_accounts.urls", namespace="ams_accounts")),
    path("requests/", include("ams.approvals.urls", namespace="ams_approvals")),
    path("subscriptions/", include("ams.subscriptions.urls", namespace="ams_subscriptions")),
    path("expenses/", include("ams.expenses.urls", namespace="ams_expenses")),
    path("admin-ams/", include("ams.audit.urls", namespace="ams_audit")),
    path("", RedirectView.as_view(url="/ams/requests/inbox/"), name="ams_home"),
]
