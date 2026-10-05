from django.conf import settings
from django.db import models

from inventory.models import Instrument


class IssueRequest(models.Model):
    """One student request for one or more instruments (a "basket").

    The request as a whole is approved, issued and returned together.
    The instruments and quantities are in IssueRequestItem.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"

    # A request is "open" until it is rejected or returned.
    OPEN_STATUSES = (Status.PENDING, Status.APPROVED, Status.ISSUED)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="issue_requests"
    )
    purpose = models.TextField()
    course_or_project = models.CharField(max_length=150, blank=True)
    # How long the student wants to keep the items, counted from the day
    # staff hand them over (due_at = issued_at + duration_days).
    duration_days = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    condition_on_issue = models.TextField(blank=True)
    condition_on_return = models.TextField(blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(duration_days__gte=1), name="request_duration_at_least_1"
            ),
        ]

    @property
    def reference(self):
        return f"REQ-{self.pk:04d}"

    def __str__(self):
        return self.reference


class IssueRequestItem(models.Model):
    """One instrument (and how many units of it) inside a request."""

    request = models.ForeignKey(IssueRequest, on_delete=models.CASCADE, related_name="items")
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="request_items"
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gte=1), name="item_quantity_at_least_1"),
            # The same instrument cannot appear twice in one request.
            models.UniqueConstraint(fields=["request", "instrument"], name="one_line_per_instrument"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.instrument.name}"


class UsageLog(models.Model):
    """History of what happened to an instrument and who it concerned."""

    class Action(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"

    # The student (or booker) the entry is about. Staff who acted are named in `note`.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="usage_logs"
    )
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="usage_logs"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self):
        return f"{self.get_action_display()}: {self.instrument.name} ({self.user.email})"
