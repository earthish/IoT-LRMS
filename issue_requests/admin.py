from django.contrib import admin, messages

from users.permissions import is_lab_assistant_or_above

from . import services
from .models import IssueRequest, IssueRequestItem, UsageLog


class ItemInline(admin.TabularInline):
    model = IssueRequestItem
    extra = 0
    readonly_fields = ("instrument", "quantity")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(IssueRequest)
class IssueRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "items_summary", "status", "requested_at", "due_at")
    list_filter = ("status", "requested_at")
    search_fields = ("user__email", "user__name", "items__instrument__name", "purpose")
    list_select_related = ("user",)
    inlines = [ItemInline]
    actions = ["approve_selected", "reject_selected", "issue_selected", "return_selected"]
    ordering = ("-requested_at",)

    # Only the two condition notes can be typed in. The status changes only
    # through the actions below, so every change follows the workflow rules
    # and is logged.
    readonly_fields = (
        "user", "purpose", "course_or_project", "duration_days", "status",
        "requested_at", "reviewed_by", "reviewed_at", "issued_at", "due_at", "returned_at",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("items__instrument")

    @admin.display(description="Items")
    def items_summary(self, obj):
        return ", ".join(str(item) for item in obj.items.all())

    # Staff only (lab assistant or faculty). No adding or deleting requests.
    def has_module_permission(self, request):
        return is_lab_assistant_or_above(request.user)

    def has_view_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_change_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def _run(self, request, queryset, step, label):
        """Apply one workflow step to each selected request, reporting each result."""
        done = 0
        for issue_request in queryset:
            try:
                step(issue_request, request.user)
                done += 1
            except services.RequestError as error:
                self.message_user(request, str(error), level=messages.ERROR)
        if done:
            self.message_user(request, f"{done} request(s) {label}.")

    @admin.action(description="Approve selected requests")
    def approve_selected(self, request, queryset):
        self._run(request, queryset, services.approve, "approved")

    @admin.action(description="Reject selected requests")
    def reject_selected(self, request, queryset):
        self._run(request, queryset, services.reject, "rejected")

    @admin.action(description="Mark selected requests as issued (items handed over)")
    def issue_selected(self, request, queryset):
        self._run(request, queryset, services.issue, "issued")

    @admin.action(description="Mark selected requests as returned")
    def return_selected(self, request, queryset):
        self._run(request, queryset, services.mark_returned, "marked as returned")


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    """A read-only history. Entries are written by the workflow, never by hand."""

    list_display = ("timestamp", "user", "instrument", "action", "note")
    list_filter = ("action", "timestamp")
    search_fields = ("user__email", "instrument__name", "note")
    list_select_related = ("user", "instrument")

    def has_module_permission(self, request):
        return is_lab_assistant_or_above(request.user)

    def has_view_permission(self, request, obj=None):
        return is_lab_assistant_or_above(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
