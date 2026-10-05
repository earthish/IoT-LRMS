"""Role checks shared by the apps. Roles always come from the logged-in user
on the server, never from anything the browser sends."""


def is_faculty(user):
    return user.is_superuser or getattr(user, "role", None) == "faculty"


def is_lab_assistant_or_above(user):
    # getattr: the admin also asks about signed-out visitors (AnonymousUser has no role).
    return user.is_superuser or getattr(user, "role", None) in ("lab_assistant", "faculty")
