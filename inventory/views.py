from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from issue_requests import basket
from issue_requests.models import IssueRequest, IssueRequestItem
from issue_requests.services import request_blocker

from . import services
from .models import Category, Instrument

PAGE_SIZE = 12


def _to_int(value):
    """Turn a query-string value into an int, or None if it is not a number."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_url(current, **changes):
    """A '?q=...&sort=...' link: the current filters with some values changed.

    Empty values are left out. "page" is not part of `current`, so changing
    a filter always goes back to page 1.
    """
    params = {**current, **changes}
    params = {key: value for key, value in params.items() if value not in ("", None)}
    return "?" + urlencode(params)


@login_required  # every signed-in role (student, lab assistant, faculty) can browse
def instrument_list(request):
    # Read the filters from the URL. Anything unexpected falls back to "no filter".
    query = request.GET.get("q", "").strip()
    category_id = _to_int(request.GET.get("category"))
    availability = request.GET.get("availability", "")
    if availability not in services.AVAILABILITY_OPTIONS:
        availability = ""
    sort = request.GET.get("sort", "name")
    if sort not in services.SORT_OPTIONS:
        sort = "name"

    results = services.search_instruments(query, category_id, availability, sort)
    page = Paginator(results, PAGE_SIZE).get_page(request.GET.get("page"))

    current = {
        "q": query,
        "category": category_id,
        "availability": availability,
        "sort": sort if sort != "name" else "",
    }

    category_chips = [
        {"label": "All", "url": _build_url(current, category=""), "active": not category_id}
    ]
    for category in Category.objects.all():
        category_chips.append(
            {
                "label": category.name,
                "url": _build_url(current, category=category.id),
                "active": category.id == category_id,
            }
        )

    availability_chips = [
        {"label": "All", "url": _build_url(current, availability=""), "active": not availability}
    ]
    for key, label in services.AVAILABILITY_OPTIONS.items():
        availability_chips.append(
            {
                "label": label,
                "url": _build_url(current, availability=key),
                "active": key == availability,
            }
        )

    context = {
        "page": page,
        "query": query,
        "category_id": category_id,
        "availability": availability,
        "sort": sort,
        "sort_options": services.SORT_OPTIONS.items(),
        "category_chips": category_chips,
        "availability_chips": availability_chips,
        "total_count": Instrument.objects.count(),
        "has_filters": bool(query or category_id or availability),
        "previous_url": _build_url(current, page=page.previous_page_number())
        if page.has_previous()
        else "",
        "next_url": _build_url(current, page=page.next_page_number())
        if page.has_next()
        else "",
    }
    return render(request, "inventory/instrument_list.html", context)


@login_required
def instrument_detail(request, pk):
    instrument = get_object_or_404(Instrument.objects.select_related("category"), pk=pk)
    instrument.badge = services.get_badge(instrument)
    # Can this person request it? (None means yes; otherwise the reason is shown.)
    already_open = IssueRequestItem.objects.filter(
        request__user=request.user,
        instrument=instrument,
        request__status__in=[IssueRequest.Status.PENDING, IssueRequest.Status.APPROVED],
    ).exists()
    context = {
        "instrument": instrument,
        "request_blocker": request_blocker(request.user, instrument),
        "open_request_exists": already_open,
        "basket_quantity": basket.quantity_of(request, instrument.pk),
    }
    return render(request, "inventory/instrument_detail.html", context)
