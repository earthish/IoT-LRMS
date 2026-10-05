"""Inventory business logic: stock badges, search, filters and sorting.

The lab has a few hundred items at most, so we load the matching rows and do
the stock-level filtering and sorting in plain Python. That keeps the rules
easy to read and explain.
"""

from collections import namedtuple

from django.db.models import Q

from .models import Instrument

# An instrument counts as "low stock" when 3 or fewer units are left,
# or when 20% or less of the total is left.
LOW_STOCK_UNITS = 3
LOW_STOCK_PERCENT = 20

# key: used by the availability filter. label: shown on the card.
# tone: which colours the template uses (blue, warn or idle).
Badge = namedtuple("Badge", ["key", "label", "tone"])

SORT_OPTIONS = {
    "name": "Name (A–Z)",
    "avail": "Most available",
    "scarce": "Least available",
}

AVAILABILITY_OPTIONS = {
    "available": "Available",
    "low": "Low stock",
    "out": "Out of stock",
}


def get_badge(instrument):
    """The status shown on a card.

    A status set by staff (in use, maintenance, reserved) always wins. When
    the status is "available", the badge depends on how many units are left.
    """
    if instrument.status != Instrument.Status.AVAILABLE:
        tones = {
            Instrument.Status.IN_USE: "warn",
            Instrument.Status.MAINTENANCE: "idle",
            Instrument.Status.RESERVED: "blue",
        }
        return Badge(
            instrument.status,
            instrument.get_status_display(),
            tones[instrument.status],
        )

    available = instrument.quantity_available
    total = instrument.quantity_total
    if available == 0:
        return Badge("out", "Out of stock", "idle")
    # Whole numbers only (no decimals), so exactly 20% counts as low.
    if available <= LOW_STOCK_UNITS or available * 100 <= total * LOW_STOCK_PERCENT:
        return Badge("low", "Low stock", "warn")
    return Badge("available", "Available", "blue")


def _fill_ratio(instrument):
    if instrument.quantity_total == 0:
        return 0
    return instrument.quantity_available / instrument.quantity_total


def search_instruments(query="", category_id=None, availability="", sort="name"):
    """Return a list of instruments (each with a .badge) matching the filters."""
    instruments = Instrument.objects.select_related("category")

    if query:
        instruments = instruments.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )
    if category_id:
        instruments = instruments.filter(category_id=category_id)

    results = list(instruments)
    for instrument in results:
        instrument.badge = get_badge(instrument)

    if availability:
        results = [i for i in results if i.badge.key == availability]

    # Python's sort is stable, so sort by name first and the name order is
    # kept for items that tie on the second sort.
    results.sort(key=lambda i: i.name.lower())
    if sort == "avail":
        results.sort(key=_fill_ratio, reverse=True)
    elif sort == "scarce":
        results.sort(key=_fill_ratio)
    return results
