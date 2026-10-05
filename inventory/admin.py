from django.contrib import admin

from .models import Category, Instrument


# The admin also calls these for signed-out visitors (to build its login page).
# An AnonymousUser has no "role", so getattr gives None instead of crashing.
def is_faculty(user):
    return user.is_superuser or getattr(user, "role", None) == "faculty"


def is_lab_assistant_or_above(user):
    return user.is_superuser or getattr(user, "role", None) in (
        "lab_assistant",
        "faculty",
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

    # Permissions come from the user's role, not from Django's per-model
    # permission checkboxes. Only faculty manage categories.
    def has_module_permission(self, request):
        return is_lab_assistant_or_above(request.user)

    def has_view_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_add_permission(self, request):
        return is_faculty(request.user)

    def has_change_permission(self, request, obj=None):
        return is_faculty(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_faculty(request.user)


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "status",
        "quantity_available",
        "quantity_total",
        "is_bookable",
    )
    list_filter = ("status", "category", "is_bookable")
    search_fields = ("name", "description")
    list_select_related = ("category",)

    # Faculty manage inventory (add, edit, delete). Lab assistants can view
    # everything and change only the status (e.g. mark under maintenance).
    def has_module_permission(self, request):
        return is_lab_assistant_or_above(request.user)

    def has_view_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_add_permission(self, request):
        return is_faculty(request.user)

    def has_change_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_faculty(request.user)

    def get_readonly_fields(self, request, obj=None):
        if is_faculty(request.user):
            return ()
        # Lab assistants: every field except status is read-only. (Read the
        # model's fields directly: get_fields() calls this method and would loop.)
        return tuple(
            f.name for f in self.model._meta.fields if f.name not in ("id", "status")
        )
