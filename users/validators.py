from django.conf import settings


def is_allowed_email(email):
    """True only if the email's domain is exactly one of ALLOWED_EMAIL_DOMAINS.

    XIM uses xim.edu.in for employees and stu.xim.edu.in for students.
    The domain must match exactly, so lookalikes such as "notxim.edu.in",
    "xim.edu.in.evil.com" or other subdomains are rejected. Case is ignored.
    """
    if not email or "@" not in email:
        return False
    domain = email.strip().lower().rsplit("@", 1)[1]
    allowed = {d.strip().lower() for d in settings.ALLOWED_EMAIL_DOMAINS}
    return domain in allowed
