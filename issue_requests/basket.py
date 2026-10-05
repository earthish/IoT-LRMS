"""The student's basket of instruments, kept in their login session.

The session stores {instrument id: quantity}. Session data is saved as JSON,
so the ids are stored as text ("3") and converted back to numbers when read.
Nothing goes into the database until the student submits the request.
"""

from inventory.models import Instrument

SESSION_KEY = "issue_basket"


def _read(request):
    return {int(pk): qty for pk, qty in request.session.get(SESSION_KEY, {}).items()}


def _write(request, contents):
    request.session[SESSION_KEY] = {str(pk): qty for pk, qty in contents.items()}


def set_item(request, instrument, quantity):
    """Add the instrument, or change its quantity if it is already there."""
    contents = _read(request)
    contents[instrument.pk] = quantity
    _write(request, contents)


def remove_item(request, instrument_id):
    contents = _read(request)
    contents.pop(instrument_id, None)
    _write(request, contents)


def clear(request):
    request.session.pop(SESSION_KEY, None)


def quantity_of(request, instrument_id):
    """How many of this instrument are in the basket (0 if none)."""
    return _read(request).get(instrument_id, 0)


def count(request):
    """Number of different instruments in the basket."""
    return len(_read(request))


def get_items(request):
    """List of (instrument, quantity) pairs, ordered by name.

    An instrument deleted since it was added is quietly left out.
    """
    contents = _read(request)
    instruments = Instrument.objects.select_related("category").in_bulk(contents.keys())
    pairs = [(instruments[pk], qty) for pk, qty in contents.items() if pk in instruments]
    return sorted(pairs, key=lambda pair: pair[0].name.lower())
