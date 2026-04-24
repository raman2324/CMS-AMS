from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for Google SSO.

    On first login (new account):
    - Populates first_name / last_name from the Google profile.
    - Defaults new users to the Employee role.
    - Records sso_provider and sso_subject so Finance Head can see
      how the account was created in Manage → View Users.
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
