from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from users.models import User

from .models import Category, Instrument


def make_instrument(**kwargs):
    category, _ = Category.objects.get_or_create(name="Sensors")
    defaults = dict(name="DHT22", category=category, quantity_total=5, quantity_available=5)
    defaults.update(kwargs)
    return Instrument.objects.create(**defaults)


class InstrumentModelTests(TestCase):
    def test_defaults(self):
        item = make_instrument()
        self.assertEqual(item.status, Instrument.Status.AVAILABLE)
        self.assertFalse(item.is_bookable)

    def test_available_cannot_exceed_total_in_form_validation(self):
        item = make_instrument(quantity_total=2, quantity_available=2)
        item.quantity_available = 3
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_available_cannot_exceed_total_in_database(self):
        # Bypasses clean(): the database constraint must still stop it.
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_instrument(quantity_total=2, quantity_available=3)

    def test_category_in_use_cannot_be_deleted(self):
        item = make_instrument()
        with self.assertRaises(ProtectedError):
            item.category.delete()


class InstrumentAdminPermissionTests(TestCase):
    def setUp(self):
        self.item = make_instrument()
        self.student = User.objects.create_user("s@stu.xim.edu.in")
        self.assistant = User.objects.create_user(
            "la@xim.edu.in", role=User.Role.LAB_ASSISTANT
        )
        self.faculty = User.objects.create_user("f@xim.edu.in", role=User.Role.FACULTY)
        self.list_url = reverse("admin:inventory_instrument_changelist")
        self.add_url = reverse("admin:inventory_instrument_add")
        self.change_url = reverse("admin:inventory_instrument_change", args=[self.item.pk])
        self.delete_url = reverse("admin:inventory_instrument_delete", args=[self.item.pk])

    def status_of(self, user, url):
        self.client.force_login(user)
        return self.client.get(url).status_code

    def test_signed_out_visitor_gets_admin_login_page(self):
        # Regression: the admin login page used to crash for anonymous users.
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.list_url).status_code, 302)

    def test_student_cannot_use_admin(self):
        # Students are not staff, so the admin redirects them to its login.
        self.assertEqual(self.status_of(self.student, self.list_url), 302)

    def test_lab_assistant_can_view_and_change_but_not_add_or_delete(self):
        self.assertEqual(self.status_of(self.assistant, self.list_url), 200)
        self.assertEqual(self.status_of(self.assistant, self.change_url), 200)
        self.assertEqual(self.status_of(self.assistant, self.add_url), 403)
        self.assertEqual(self.status_of(self.assistant, self.delete_url), 403)

    def test_lab_assistant_can_only_change_status(self):
        self.client.force_login(self.assistant)
        response = self.client.get(self.change_url)
        form_fields = response.context["adminform"].form.fields
        self.assertEqual(list(form_fields), ["status"])

    def test_faculty_can_add_change_and_delete(self):
        for url in (self.list_url, self.add_url, self.change_url, self.delete_url):
            with self.subTest(url=url):
                self.assertEqual(self.status_of(self.faculty, url), 200)
