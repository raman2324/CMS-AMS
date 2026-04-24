from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for Google SSO.

    populate_user  — called for new accounts: extracts name from Google profile.
    save_user      — called for new accounts: sets default role + SSO tracking fields.
    pre_social_login — called on EVERY login (new + existing): syncs missing name /
                       SSO fields so existing users' names appear in Manage → View Users.
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
        user = super().save_user(request, sociallogin, form)

        # Default new SSO users to Employee — Finance Head can promote them
        # via Manage → View Users if a different role is needed.
        user.role = user.__class__.ROLE_EMPLOYEE

        # Record which SSO provider created this account.
        user.sso_provider = sociallogin.account.provider   # "google"
        user.sso_subject = sociallogin.account.uid         # Google's unique user ID

        user.save(update_fields=["role", "sso_provider", "sso_subject"])
        return user

    def pre_social_login(self, request, sociallogin):
        """
        Called on every SSO login — both new and returning users.
        For existing accounts: sync any missing name / SSO fields so the user
        immediately appears with their full name in Finance Head → Manage → View Users.
        """
        super().pre_social_login(request, sociallogin)

        user = sociallogin.user
        if not user.pk:
            # Brand-new account — populate_user + save_user handle this.
            return

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
