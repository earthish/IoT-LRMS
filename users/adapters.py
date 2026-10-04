"""allauth adapters that make Google (with a verified @xim.edu.in email) the
only way to sign in.

Why this is needed: the "hd" parameter we send to Google only filters the
account picker. Anyone can strip it from the URL and log in with a gmail.com
account, so the domain must be checked here, on the server, after Google has
told us who the user is.
"""

import logging

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import render

from .validators import is_allowed_email

logger = logging.getLogger(__name__)


def get_google_email(sociallogin):
    """Email address Google returned for *this* login attempt.

    We read Google's data (extra_data), not sociallogin.user.email: for a
    returning user, allauth has already swapped sociallogin.user for the
    stored database row, which could be stale.
    """
    return (sociallogin.account.extra_data or {}).get("email", "")


def is_google_email_verified(sociallogin):
    """True if Google says it has verified the email address.

    Google's ID token uses "email_verified"; the older userinfo API uses
    "verified_email". Accept either, but only if it is actually true.
    """
    data = sociallogin.account.extra_data or {}
    return data.get("email_verified") is True or data.get("verified_email") is True


def is_allowed_sociallogin(sociallogin):
    """The single rule: a verified email on the university domain."""
    email = get_google_email(sociallogin)
    return is_allowed_email(email) and is_google_email_verified(sociallogin)


class XimAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # No local (email + password) signup. Accounts are only created
        # through Google, which is decided by XimSocialAccountAdapter below.
        return False


class XimSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Runs after Google has authenticated the user but before Django
        # logs them in, for both new and returning users. Raising
        # ImmediateHttpResponse aborts the login and shows our page instead.
        if not is_allowed_sociallogin(sociallogin):
            logger.warning(
                "Rejected Google login: email=%r verified=%s",
                get_google_email(sociallogin),
                is_google_email_verified(sociallogin),
            )
            response = render(request, "users/login_rejected.html", status=403)
            raise ImmediateHttpResponse(response)

    def is_open_for_signup(self, request, sociallogin):
        # Second check at the moment a new account would be created, in case
        # pre_social_login is ever bypassed. (The default would ask
        # XimAccountAdapter, which says False, and block everyone.)
        return is_allowed_sociallogin(sociallogin)

    def populate_user(self, request, sociallogin, data):
        # Fills a *new* user from Google's profile. The role is never set here,
        # so it stays at the model default (student). Roles are only changed
        # by a superuser or faculty in the admin.
        user = super().populate_user(request, sociallogin, data)
        user.email = (user.email or "").lower()
        full_name = (sociallogin.account.extra_data or {}).get("name", "")
        user.name = full_name or f"{user.first_name} {user.last_name}".strip()
        return user
