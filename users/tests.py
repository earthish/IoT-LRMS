from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from .adapters import XimAccountAdapter, XimSocialAccountAdapter
from .admin import UserAdmin
from .forms import GoogleSignupForm
from .models import User
from .validators import is_allowed_email


def make_sociallogin(email, verified=True, name="Test Student"):
    """A SocialLogin shaped like the one allauth builds after Google login."""
    extra_data = {"email": email, "email_verified": verified, "name": name}
    account = SocialAccount(provider="google", uid="123", extra_data=extra_data)
    return SocialLogin(user=User(email=email), account=account)


class AllowedEmailTests(TestCase):
    def test_university_email_allowed(self):
        self.assertTrue(is_allowed_email("student@xim.edu.in"))

    def test_student_domain_allowed(self):
        self.assertTrue(is_allowed_email("ucse24044@stu.xim.edu.in"))

    def test_case_is_ignored(self):
        self.assertTrue(is_allowed_email("Student@STU.XIM.EDU.IN"))

    def test_other_domains_rejected(self):
        for email in [
            "someone@gmail.com",
            "a@notxim.edu.in",  # lookalike prefix
            "a@xim.edu.in.evil.com",  # lookalike suffix
            "a@stu.xim.edu.in.evil.com",  # lookalike suffix on a subdomain
            "a@evil-xim.edu.in",  # lookalike with no "." before xim
            "a@staff.xim.edu.in",  # subdomain not in the allowed list
            "xim.edu.in",  # no "@"
            "",
            None,
        ]:
            with self.subTest(email=email):
                self.assertFalse(is_allowed_email(email))


class SocialAdapterTests(TestCase):
    def setUp(self):
        self.adapter = XimSocialAccountAdapter()
        self.request = RequestFactory().get("/accounts/google/login/callback/")

    def assert_rejected(self, sociallogin):
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            self.adapter.pre_social_login(self.request, sociallogin)
        self.assertEqual(ctx.exception.response.status_code, 403)
        self.assertFalse(self.adapter.is_open_for_signup(self.request, sociallogin))

    def test_non_xim_email_rejected(self):
        self.assert_rejected(make_sociallogin("someone@gmail.com"))

    def test_unverified_xim_email_rejected(self):
        self.assert_rejected(make_sociallogin("student@xim.edu.in", verified=False))

    def test_missing_email_rejected(self):
        self.assert_rejected(make_sociallogin(""))

    def test_verified_xim_email_accepted(self):
        sociallogin = make_sociallogin("ucse24044@stu.xim.edu.in")
        self.adapter.pre_social_login(self.request, sociallogin)  # no exception
        self.assertTrue(self.adapter.is_open_for_signup(self.request, sociallogin))

    def test_returning_user_checked_against_google_data(self):
        # Stored user looks fine, but Google now reports a non-xim email.
        sociallogin = make_sociallogin("someone@gmail.com")
        sociallogin.user = User(email="student@xim.edu.in")
        self.assert_rejected(sociallogin)

    def test_new_user_is_student_with_name_from_google(self):
        sociallogin = make_sociallogin("Student@xim.edu.in", name="Asha Rao")
        user = self.adapter.populate_user(
            self.request, sociallogin, {"email": "Student@xim.edu.in"}
        )
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.email, "student@xim.edu.in")
        self.assertEqual(user.name, "Asha Rao")


class ExistingAccountLinkTests(TestCase):
    def test_google_login_uses_existing_account_with_same_email(self):
        admin = User.objects.create_superuser("ucse24044@stu.xim.edu.in", "pass12345!")
        sociallogin = make_sociallogin("ucse24044@stu.xim.edu.in")
        sociallogin.email_addresses = [
            EmailAddress(email="ucse24044@stu.xim.edu.in", verified=True, primary=True)
        ]
        # allauth runs lookup() inside a request right after Google returns.
        request = RequestFactory().get("/")
        with context.request_context(request):
            sociallogin.provider = sociallogin.account.get_provider(request)
            sociallogin.lookup()
        self.assertEqual(sociallogin.user, admin)


class GoogleSignupFormTests(TestCase):
    def test_typed_email_is_ignored(self):
        sociallogin = make_sociallogin("ucse24044@stu.xim.edu.in")
        form = GoogleSignupForm(
            data={"email": "professor@xim.edu.in"}, sociallogin=sociallogin
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "ucse24044@stu.xim.edu.in")


class LocalLoginDisabledTests(TestCase):
    def test_local_signup_closed(self):
        request = RequestFactory().get("/")
        self.assertFalse(XimAccountAdapter().is_open_for_signup(request))

    def test_password_login_rejected(self):
        User.objects.create_user("student@xim.edu.in", password="pass12345!")
        response = self.client.post(
            "/accounts/login/",
            {"login": "student@xim.edu.in", "password": "pass12345!"},
        )
        self.assertEqual(response.status_code, 403)

    def test_signup_and_password_reset_pages_do_not_exist(self):
        for url in ["/accounts/signup/", "/accounts/password/reset/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class UserModelTests(TestCase):
    def test_new_user_defaults_to_student(self):
        user = User.objects.create_user("student@xim.edu.in")
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertFalse(user.has_usable_password())

    def test_email_is_lowercased(self):
        user = User.objects.create_user("Student@XIM.edu.in")
        self.assertEqual(user.email, "student@xim.edu.in")

    def test_superuser_is_faculty(self):
        user = User.objects.create_superuser("admin@xim.edu.in", "pass12345!")
        self.assertEqual(user.role, User.Role.FACULTY)
        self.assertTrue(user.is_superuser)

    def test_blank_roll_numbers_do_not_clash(self):
        User.objects.create_user("a@xim.edu.in", roll_number="")
        User.objects.create_user("b@xim.edu.in", roll_number="")
        self.assertEqual(User.objects.filter(roll_number__isnull=True).count(), 2)

    def test_role_helpers(self):
        student = User(role=User.Role.STUDENT)
        assistant = User(role=User.Role.LAB_ASSISTANT)
        faculty = User(role=User.Role.FACULTY)
        self.assertFalse(student.is_lab_assistant_or_above)
        self.assertTrue(assistant.is_lab_assistant_or_above)
        self.assertFalse(assistant.is_faculty_role)
        self.assertTrue(faculty.is_faculty_role)


class AdminRolePermissionTests(TestCase):
    def setUp(self):
        self.model_admin = UserAdmin(User, AdminSite())
        self.target = User.objects.create_user("student@xim.edu.in")

    def readonly_for(self, editor):
        request = RequestFactory().get("/admin/")
        request.user = editor
        return self.model_admin.get_readonly_fields(request, self.target)

    def test_lab_assistant_cannot_change_roles(self):
        editor = User.objects.create_user(
            "la@xim.edu.in", role=User.Role.LAB_ASSISTANT, is_staff=True
        )
        self.assertIn("role", self.readonly_for(editor))

    def test_faculty_can_change_roles_but_not_superuser_flag(self):
        editor = User.objects.create_user(
            "fac@xim.edu.in", role=User.Role.FACULTY, is_staff=True
        )
        readonly = self.readonly_for(editor)
        self.assertNotIn("role", readonly)
        self.assertIn("is_superuser", readonly)

    def test_superuser_can_change_everything(self):
        editor = User.objects.create_superuser("admin@xim.edu.in", "pass12345!")
        readonly = self.readonly_for(editor)
        self.assertNotIn("role", readonly)
        self.assertNotIn("is_superuser", readonly)


class HomePageTests(TestCase):
    def test_logged_out_visitor_is_sent_to_login(self):
        response = self.client.get("/")
        self.assertRedirects(
            response, "/accounts/login/?next=/", fetch_redirect_response=False
        )

    def test_logged_in_user_sees_email_and_role(self):
        user = User.objects.create_user("ucse24044@stu.xim.edu.in")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, "ucse24044@stu.xim.edu.in")
        self.assertContains(response, "Student")
        self.assertNotContains(response, "/admin/")  # students are not staff


class StaffFlagTests(TestCase):
    def test_is_staff_follows_role(self):
        user = User.objects.create_user("x@xim.edu.in")
        self.assertFalse(user.is_staff)  # students are not staff
        for role in (User.Role.LAB_ASSISTANT, User.Role.FACULTY):
            user.role = role
            user.save()
            self.assertTrue(user.is_staff)
        user.role = User.Role.STUDENT  # demoted again
        user.save()
        self.assertFalse(user.is_staff)

    def test_superuser_keeps_staff(self):
        admin = User.objects.create_superuser("admin@xim.edu.in", "pass12345!")
        admin.save()
        self.assertTrue(admin.is_staff)
