from django import forms

from .services import MAX_LOAN_DAYS


class AddToBasketForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1)


class SubmitRequestForm(forms.Form):
    purpose = forms.CharField(
        min_length=15,
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"min_length": "Tell the lab what you will use the items for (at least 15 characters)."},
    )
    course_or_project = forms.CharField(max_length=150, required=False)
    duration_days = forms.IntegerField(
        min_value=1,
        max_value=MAX_LOAN_DAYS,
        error_messages={
            "min_value": "Choose at least 1 day.",
            "max_value": f"The longest loan is {MAX_LOAN_DAYS} days.",
        },
    )
    agree = forms.BooleanField(
        error_messages={"required": "Please confirm you will return the items on time."}
    )
