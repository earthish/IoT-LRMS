from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.models import Instrument

from . import basket, services
from .forms import AddToBasketForm, SubmitRequestForm
from .models import IssueRequest

PAGE_SIZE = 10


@login_required
@require_POST
def basket_add(request, instrument_id):
    """'Add to request' button on an instrument page (also used to change a quantity)."""
    instrument = get_object_or_404(Instrument, pk=instrument_id)
    form = AddToBasketForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a quantity of at least 1.")
        return redirect("inventory:detail", pk=instrument.pk)

    quantity = form.cleaned_data["quantity"]
    reason = services.request_blocker(request.user, instrument, quantity)
    if reason:
        messages.error(request, reason)
        return redirect("inventory:detail", pk=instrument.pk)

    basket.set_item(request, instrument, quantity)
    messages.success(request, f"Added {quantity} × {instrument.name} to your request.")
    return redirect("inventory:list")


@login_required
@require_POST
def basket_update(request, instrument_id):
    """Change a quantity from the basket page."""
    instrument = get_object_or_404(Instrument, pk=instrument_id)
    form = AddToBasketForm(request.POST)
    if form.is_valid():
        quantity = form.cleaned_data["quantity"]
        reason = services.request_blocker(request.user, instrument, quantity)
        if reason:
            messages.error(request, reason)
        else:
            basket.set_item(request, instrument, quantity)
    else:
        messages.error(request, "Choose a quantity of at least 1.")
    return redirect("issue_requests:basket")


@login_required
@require_POST
def basket_remove(request, instrument_id):
    basket.remove_item(request, instrument_id)
    return redirect("issue_requests:basket")


@login_required
def basket_view(request):
    """Show the basket (GET) and submit it as a request (POST)."""
    items = basket.get_items(request)

    if request.method == "POST":
        form = SubmitRequestForm(request.POST)
        if form.is_valid():
            try:
                issue_request = services.create_request(
                    request.user,
                    items,
                    form.cleaned_data["purpose"],
                    form.cleaned_data["course_or_project"],
                    form.cleaned_data["duration_days"],
                )
            except services.RequestError as error:
                messages.error(request, str(error))
            else:
                basket.clear(request)
                messages.success(
                    request, f"{issue_request.reference} submitted. A lab assistant will review it."
                )
                return redirect("issue_requests:list")
    else:
        form = SubmitRequestForm(initial={"duration_days": 14})

    return render(
        request,
        "issue_requests/basket.html",
        {"items": items, "form": form, "max_loan_days": services.MAX_LOAN_DAYS},
    )


@login_required
def my_requests(request):
    """The signed-in user's own requests only (never anyone else's)."""
    requests = (
        IssueRequest.objects.filter(user=request.user)
        .prefetch_related("items__instrument")
        .order_by("-requested_at")
    )
    page = Paginator(requests, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "issue_requests/my_requests.html", {"page": page})
