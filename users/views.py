from django.contrib.auth.decorators import login_required
from django.shortcuts import render


# Landing page shown after Google login (and at "/").
@login_required  # logged-out visitors are sent to /accounts/login/
def home(request):
    return render(request, "users/home.html")
