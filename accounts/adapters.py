from django.contrib.auth import get_user_model
from django.shortcuts import redirect

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Google SSO adapter with auto-registration.

    - Approved domain, user exists in DB  → log in, sync name fields
    - Approved domain, user NOT in DB     → auto-create as viewer, log in
    - Non-approved domain                 → blocked by allauth WHITELISTED_DOMAINS
                                            before this adapter is even reached
    """

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)

        if not sociallogin.is_existing:
            email = (sociallogin.user.email or "").strip()
            if not email:
                raise self._redirect_error(
                    request,
                    "Your Google account has no email address. Please contact your Finance Head.",
                )

            User = get_user_model()
            extra = sociallogin.account.extra_data or {}

            try:
                db_user = User.objects.get(email__iexact=email)
                self._sync_fields(db_user, extra, sociallogin)
            except User.DoesNotExist:
                # First SSO login from approved domain — register as viewer
                db_user = User(
                    email=email,
                    username=self._unique_username(email),
                    first_name=extra.get("given_name", ""),
                    last_name=extra.get("family_name", ""),
                    role="viewer",
                    sso_provider=sociallogin.account.provider,
                    sso_subject=sociallogin.account.uid,
                )
                db_user.set_unusable_password()
                db_user.save()

            sociallogin.user = db_user
            sociallogin.save(request, connect=True)
            return

        # Returning SSO user — sync any missing name/SSO fields
        self._sync_fields(sociallogin.user, sociallogin.account.extra_data or {}, sociallogin)

    # ------------------------------------------------------------------

    def _sync_fields(self, user, extra, sociallogin):
        changed = []
        if not user.first_name and extra.get("given_name"):
            user.first_name = extra["given_name"]
            changed.append("first_name")
        if not user.last_name and extra.get("family_name"):
            user.last_name = extra["family_name"]
            changed.append("last_name")
        if not user.sso_provider:
            user.sso_provider = sociallogin.account.provider
            user.sso_subject = sociallogin.account.uid
            changed += ["sso_provider", "sso_subject"]
        if changed:
            user.save(update_fields=changed)

    def _unique_username(self, email):
        User = get_user_model()
        base = email.split("@")[0].replace(".", "_").replace("-", "_")
        username, i = base, 1
        while User.objects.filter(username=username).exists():
            username = f"{base}_{i}"
            i += 1
        return username

    def _redirect_error(self, request, message):
        from django.contrib import messages as django_messages
        from allauth.core.exceptions import ImmediateHttpResponse
        django_messages.error(request, message)
        return ImmediateHttpResponse(redirect("/login/"))
