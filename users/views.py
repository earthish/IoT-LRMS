from django.contrib.auth.decorators import login_required
from django.shortcuts import render


# TEMPORARY: a plain landing page so there is somewhere to go after Google
# login. Remove it when the React frontend takes over "/".
@login_required  # logged-out visitors are sent to /accounts/login/
def home(request):
    return render(request, "users/home.html")
