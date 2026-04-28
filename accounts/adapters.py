from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Google SSO adapter that enforces pre-registration.

    Only users that a Finance Head has explicitly added to the system may log
    in via SSO.  Any Google account whose email is not already in the User
    table is blocked with a friendly error and redirected back to /login/.

    pre_social_login is called on every SSO attempt:
      - Email not in DB               → blocked (ImmediateHttpResponse)
      - Email in DB, first SSO login  → social account linked to that user,
                                        missing name/SSO fields synced
      - Returning SSO user            → missing name/SSO fields synced
    """

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)

        if not sociallogin.is_existing:
            # allauth found no SocialAccount for this Google UID.
            # Check whether the Finance Head has pre-registered this email.
            email = (sociallogin.user.email or "").strip()
            if not email:
                messages.error(
                    request,
                    "Your Google account has no email address. "
                    "Please contact your Finance Head.",
                )
                raise ImmediateHttpResponse(redirect("/login/"))

            User = get_user_model()
            try:
                db_user = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                messages.error(
                    request,
                    "Your account has not been set up yet. "
                    "Please ask your Finance Head to add you.",
                )
                raise ImmediateHttpResponse(redirect("/login/"))

            # Pre-registered — sync name/SSO fields, then wire up the
            # SocialAccount so allauth treats this as an existing-user login.
            extra = sociallogin.account.extra_data or {}
            changed = []
            if not db_user.first_name and extra.get("given_name"):
                db_user.first_name = extra["given_name"]
                changed.append("first_name")
            if not db_user.last_name and extra.get("family_name"):
                db_user.last_name = extra["family_name"]
                changed.append("last_name")
            if not db_user.sso_provider:
                db_user.sso_provider = sociallogin.account.provider
                db_user.sso_subject = sociallogin.account.uid
                changed += ["sso_provider", "sso_subject"]
            if changed:
                db_user.save(update_fields=changed)

            # Setting sociallogin.user to a DB-backed user makes is_existing
            # True, so allauth calls _login() instead of process_signup().
            # save(connect=True) persists the SocialAccount link so subsequent
            # logins go through the fast SocialAccount lookup path.
            sociallogin.user = db_user
            sociallogin.save(request, connect=True)
            return

        # Returning SSO user — sync any missing name / SSO fields.
        user = sociallogin.user
        extra = sociallogin.account.extra_data or {}
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
