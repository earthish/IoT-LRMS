from allauth.socialaccount.forms import SignupForm


class GoogleSignupForm(SignupForm):
    """allauth's "complete your sign-up" form, with the email locked.

    allauth falls back to this form in some cases (for example when the email
    is already taken). By default the email box is editable and allauth saves
    whatever was typed, which would let someone sign in with Google and then
    claim a different address. A disabled field makes Django ignore the posted
    value and always use the initial one: the email Google verified.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].disabled = True
