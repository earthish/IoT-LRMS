"""The issue request workflow.

    pending -> approved -> issued -> returned
        \\-> rejected

Stock changes only when items are issued (units go out) and returned (units
come back). Approving does not reserve stock.

Every function that changes data runs inside transaction.atomic() and locks
the rows it changes with select_for_update(), so two staff members cannot
approve the same request twice or hand out the last unit twice. (SQLite
ignores row locks; PostgreSQL, which we will deploy on, enforces them.)
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from inventory.models import Instrument

from .models import IssueRequest, IssueRequestItem, UsageLog

MAX_LOAN_DAYS = 30


class RequestError(Exception):
    """A rule was broken. The message is safe to show to the user."""


# ---------------------------------------------------------------- requesting


def request_blocker(user, instrument, quantity=1):
    """Why this user cannot request this instrument, or None if they can."""
    if instrument.is_bookable:
        return f"{instrument.name} is a shared resource. It is booked by time slot, not issued."
    if instrument.status != Instrument.Status.AVAILABLE:
        return f"{instrument.name} is not available right now ({instrument.get_status_display().lower()})."
    if instrument.quantity_available == 0:
        return f"{instrument.name} is out of stock."
    if quantity < 1:
        return "Choose a quantity of at least 1."
    if quantity > instrument.quantity_available:
        return f"Only {instrument.quantity_available} of {instrument.name} available."
    already_open = IssueRequestItem.objects.filter(
        request__user=user,
        instrument=instrument,
        request__status__in=[IssueRequest.Status.PENDING, IssueRequest.Status.APPROVED],
    ).exists()
    if already_open:
        return f"You already have an open request for {instrument.name}."
    return None


def _log(user, instrument, action, note=""):
    UsageLog.objects.create(user=user, instrument=instrument, action=action, note=note)


def create_request(user, basket_items, purpose, course_or_project, duration_days):
    """Turn the basket ((instrument, quantity) pairs) into a pending request."""
    if not basket_items:
        raise RequestError("Your basket is empty.")
    if not 1 <= duration_days <= MAX_LOAN_DAYS:
        raise RequestError(f"Choose a loan period of 1 to {MAX_LOAN_DAYS} days.")

    with transaction.atomic():
        # Stock may have changed since the item went into the basket, so check again.
        for instrument, quantity in basket_items:
            reason = request_blocker(user, instrument, quantity)
            if reason:
                raise RequestError(reason)

        issue_request = IssueRequest.objects.create(
            user=user,
            purpose=purpose,
            course_or_project=course_or_project,
            duration_days=duration_days,
        )
        for instrument, quantity in basket_items:
            IssueRequestItem.objects.create(
                request=issue_request, instrument=instrument, quantity=quantity
            )
            _log(user, instrument, UsageLog.Action.REQUESTED, f"{issue_request.reference}: {quantity} requested")
    return issue_request


# ------------------------------------------------------------ staff actions


def _lock_request(issue_request, required_status):
    """Re-read the request with a lock and check it is in the right state."""
    locked = IssueRequest.objects.select_for_update().get(pk=issue_request.pk)
    if locked.status != required_status:
        raise RequestError(
            f"{locked.reference} is {locked.get_status_display().lower()}, "
            f"so this action does not apply."
        )
    return locked


def _log_all_items(issue_request, action, note):
    for item in issue_request.items.select_related("instrument"):
        _log(issue_request.user, item.instrument, action, note)


def approve(issue_request, staff):
    with transaction.atomic():
        locked = _lock_request(issue_request, IssueRequest.Status.PENDING)
        locked.status = IssueRequest.Status.APPROVED
        locked.reviewed_by = staff
        locked.reviewed_at = timezone.now()
        locked.save()
        _log_all_items(locked, UsageLog.Action.APPROVED, f"{locked.reference} approved by {staff.email}")
    return locked


def reject(issue_request, staff, reason=""):
    with transaction.atomic():
        locked = _lock_request(issue_request, IssueRequest.Status.PENDING)
        locked.status = IssueRequest.Status.REJECTED
        locked.reviewed_by = staff
        locked.reviewed_at = timezone.now()
        locked.save()
        note = f"{locked.reference} rejected by {staff.email}"
        _log_all_items(locked, UsageLog.Action.REJECTED, f"{note}: {reason}" if reason else note)
    return locked


def issue(issue_request, staff):
    """Hand the items over: take the units out of stock and set the due date.

    All or nothing: if any item has too few units left, nothing changes.
    """
    with transaction.atomic():
        locked = _lock_request(issue_request, IssueRequest.Status.APPROVED)
        items = list(locked.items.select_related("instrument"))

        # Lock every instrument involved, always in the same order (by id),
        # so two staff members issuing overlapping requests cannot deadlock.
        instrument_ids = sorted(item.instrument_id for item in items)
        stock = {
            i.pk: i
            for i in Instrument.objects.select_for_update().filter(pk__in=instrument_ids).order_by("pk")
        }
        for item in items:
            instrument = stock[item.instrument_id]
            if instrument.quantity_available < item.quantity:
                raise RequestError(
                    f"Cannot issue {locked.reference}: only {instrument.quantity_available} of "
                    f"{instrument.name} left, {item.quantity} needed."
                )
        for item in items:
            instrument = stock[item.instrument_id]
            instrument.quantity_available -= item.quantity
            instrument.save(update_fields=["quantity_available"])

        now = timezone.now()
        locked.status = IssueRequest.Status.ISSUED
        locked.issued_at = now
        locked.due_at = now + timedelta(days=locked.duration_days)
        locked.save()
        _log_all_items(locked, UsageLog.Action.ISSUED, f"{locked.reference} issued by {staff.email}")
    return locked


def mark_returned(issue_request, staff):
    """Take the items back: put the units back in stock."""
    with transaction.atomic():
        locked = _lock_request(issue_request, IssueRequest.Status.ISSUED)
        items = list(locked.items.select_related("instrument"))

        instrument_ids = sorted(item.instrument_id for item in items)
        stock = {
            i.pk: i
            for i in Instrument.objects.select_for_update().filter(pk__in=instrument_ids).order_by("pk")
        }
        for item in items:
            instrument = stock[item.instrument_id]
            # Never show more units than the lab owns.
            instrument.quantity_available = min(
                instrument.quantity_total, instrument.quantity_available + item.quantity
            )
            instrument.save(update_fields=["quantity_available"])

        locked.status = IssueRequest.Status.RETURNED
        locked.returned_at = timezone.now()
        locked.save()
        _log_all_items(locked, UsageLog.Action.RETURNED, f"{locked.reference} returned, received by {staff.email}")
    return locked
