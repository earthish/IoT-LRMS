from . import basket
from .models import IssueRequest


def requests_summary(request):
    """Numbers shown in the navbar: items in the basket and the user's open requests."""
    # Pages rendered without the login middleware (e.g. some error pages) have no user.
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        "basket_count": basket.count(request),
        "open_request_count": IssueRequest.objects.filter(
            user=user, status__in=IssueRequest.OPEN_STATUSES
        ).count(),
    }
