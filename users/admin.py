from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "name", "role", "department", "is_staff")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("email", "name", "roll_number")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "role", "department", "roll_number")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # Only a superuser or faculty may change roles.
        if not (request.user.is_superuser or request.user.role == User.Role.FACULTY):
            readonly.append("role")
        # Privilege flags are superuser-only, so faculty cannot make themselves superusers.
        if not request.user.is_superuser:
            readonly += ["is_staff", "is_superuser", "groups", "user_permissions"]
        return readonly
