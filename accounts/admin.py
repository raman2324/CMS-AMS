from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "get_full_name", "role", "department", "is_active"]
    list_filter = ["role", "is_active", "is_staff"]
    search_fields = ["username", "email", "first_name", "last_name"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("HR Platform", {"fields": ("role", "department", "sso_provider", "sso_subject")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("HR Platform", {"fields": ("role", "department")}),
    )
