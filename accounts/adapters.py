from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages as django_messages
from django.http import HttpResponseRedirect


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for Google SSO.

    populate_user  — called for new accounts: extracts name from Google profile.
    save_user      — called for new accounts: sets default role + SSO tracking fields.
    pre_social_login — called on EVERY login (new + existing): enforces the
                       pre-approval gate (only Finance Head-added accounts may use SSO)
                       and syncs missing name / SSO fields for existing users.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)

        # Google returns given_name / family_name in extra_data.
        # Use them if allauth's default populate_user left the fields empty.
        extra = sociallogin.account.extra_data or {}
        if not user.first_name:
            user.first_name = extra.get("given_name", "")
        if not user.last_name:
            user.last_name = extra.get("family_name", "")

        return user

    def save_user(self, request, sociallogin, form=None):
        # save_user is only called for brand-new accounts (first SSO login).
        # In normal operation this path is unreachable because pre_social_login
        # blocks any email that was not pre-created by a Finance Head.
        user = super().save_user(request, sociallogin, form)

        # Record which SSO provider created this account.
        user.sso_provider = sociallogin.account.provider   # "google"
        user.sso_subject = sociallogin.account.uid         # Google's unique user ID

        user.save(update_fields=["sso_provider", "sso_subject"])
        return user

    def pre_social_login(self, request, sociallogin):
        """
        Called on every SSO login — both new and returning users.

        Gate: only accounts whose email was pre-created by a Finance Head may
        sign in via Google SSO.  If the email does not exist in the database,
        the attempt is blocked immediately with a clear error message.

        For accounts that pass the gate: sync any missing name / SSO fields so
        the user immediately appears with their full name in Finance Head →
        Manage → View Users.
        """
        super().pre_social_login(request, sociallogin)

        user = sociallogin.user
        if not user.pk:
            # super() ran the email-lookup and still found no matching account.
            # This email was not pre-approved — block access.
            email = (user.email or "").lower()
            django_messages.error(
                request,
                f"Access denied: {email or 'your account'} has not been added to the system. "
                "Please contact your Finance Head to be granted access.",
            )
            raise ImmediateHttpResponse(HttpResponseRedirect("/login/"))

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
