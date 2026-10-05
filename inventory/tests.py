from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from users.models import User

from . import services
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


class BadgeTests(TestCase):
    """The stock rule: low stock = 3 or fewer left, or 20% or less of the total."""

    def badge_key(self, available, total, **kwargs):
        item = make_instrument(
            name=f"item-{available}-{total}-{kwargs.get('status', '')}",
            quantity_total=total,
            quantity_available=available,
            **kwargs,
        )
        return services.get_badge(item).key

    def test_stock_levels(self):
        self.assertEqual(self.badge_key(0, 20), "out")
        self.assertEqual(self.badge_key(3, 20), "low")  # 3 units left
        self.assertEqual(self.badge_key(4, 20), "low")  # exactly 20%
        self.assertEqual(self.badge_key(5, 20), "available")  # 25%
        self.assertEqual(self.badge_key(2, 10), "low")
        self.assertEqual(self.badge_key(18, 25), "available")

    def test_staff_status_wins_over_stock(self):
        self.assertEqual(
            self.badge_key(10, 10, status=Instrument.Status.MAINTENANCE), "maintenance"
        )
        self.assertEqual(self.badge_key(0, 5, status=Instrument.Status.IN_USE), "in_use")

    def test_availability_percent(self):
        self.assertEqual(make_instrument(name="a", quantity_total=20, quantity_available=3).availability_percent, 15)
        self.assertEqual(make_instrument(name="b", quantity_total=0, quantity_available=0).availability_percent, 0)


class SearchTests(TestCase):
    def setUp(self):
        sensors = Category.objects.create(name="Sensors")
        boards = Category.objects.create(name="Microcontrollers")
        self.dht = make_instrument(name="DHT22", category=sensors, description="Temperature sensor", quantity_total=30, quantity_available=22)
        self.uno = make_instrument(name="Arduino Uno", category=boards, quantity_total=25, quantity_available=18)
        self.pico = make_instrument(name="Pico W", category=boards, quantity_total=8, quantity_available=0)
        self.sonar = make_instrument(name="HC-SR04", category=sensors, quantity_total=20, quantity_available=3)

    def names(self, **kwargs):
        return [i.name for i in services.search_instruments(**kwargs)]

    def test_no_filters_returns_everything_sorted_by_name(self):
        self.assertEqual(self.names(), ["Arduino Uno", "DHT22", "HC-SR04", "Pico W"])

    def test_search_matches_name_description_and_category(self):
        self.assertEqual(self.names(query="uno"), ["Arduino Uno"])
        self.assertEqual(self.names(query="temperature"), ["DHT22"])
        self.assertEqual(self.names(query="microcontrollers"), ["Arduino Uno", "Pico W"])

    def test_category_filter(self):
        self.assertEqual(self.names(category_id=self.dht.category_id), ["DHT22", "HC-SR04"])

    def test_availability_filter(self):
        self.assertEqual(self.names(availability="out"), ["Pico W"])
        self.assertEqual(self.names(availability="low"), ["HC-SR04"])
        self.assertEqual(self.names(availability="available"), ["Arduino Uno", "DHT22"])

    def test_sorting_by_availability(self):
        # fill ratios: DHT22 0.73, Uno 0.72, HC-SR04 0.15, Pico 0
        self.assertEqual(self.names(sort="avail"), ["DHT22", "Arduino Uno", "HC-SR04", "Pico W"])
        self.assertEqual(self.names(sort="scarce"), ["Pico W", "HC-SR04", "Arduino Uno", "DHT22"])


class InventoryPageTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user("s@stu.xim.edu.in", name="Asha Rao")
        self.item = make_instrument(name="DHT22", quantity_total=30, quantity_available=22)

    def test_signed_out_visitors_are_sent_to_login(self):
        for url in (reverse("inventory:list"), reverse("inventory:detail", args=[self.item.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/accounts/login/"))

    def test_list_shows_instruments_and_counts(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("inventory:list"))
        self.assertContains(response, "DHT22")
        self.assertContains(response, "Showing <strong")
        self.assertNotContains(response, "No items match")

    def test_list_filters_from_the_url(self):
        make_instrument(name="Relay", category=self.item.category, quantity_total=5, quantity_available=5)
        self.client.force_login(self.student)
        response = self.client.get(reverse("inventory:list"), {"q": "relay"})
        self.assertContains(response, "Relay")
        self.assertNotContains(response, "DHT22")

    def test_no_match_shows_empty_state(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("inventory:list"), {"q": "zzzz"})
        self.assertContains(response, "No items match")

    def test_bad_url_values_are_ignored(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("inventory:list"),
            {"category": "abc", "availability": "nope", "sort": "nope", "page": "x"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DHT22")

    def test_pagination(self):
        for n in range(15):  # 16 items in total, 12 per page
            make_instrument(name=f"Part {n:02d}")
        self.client.force_login(self.student)
        first = self.client.get(reverse("inventory:list"))
        self.assertEqual(len(first.context["page"].object_list), 12)
        second = self.client.get(reverse("inventory:list"), {"page": 2})
        self.assertEqual(len(second.context["page"].object_list), 4)

    def test_detail_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("inventory:detail", args=[self.item.pk]))
        self.assertContains(response, "DHT22")
        self.assertContains(response, "22")
        self.assertEqual(self.client.get(reverse("inventory:detail", args=[9999])).status_code, 404)

    def test_admin_link_only_for_staff(self):
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse("inventory:list")), "/admin/")
        faculty = User.objects.create_user("f@xim.edu.in", role=User.Role.FACULTY)
        self.client.force_login(faculty)
        self.assertContains(self.client.get(reverse("inventory:list")), "/admin/")


class SeedInventoryTests(TestCase):
    def test_seed_adds_items_and_can_run_twice(self):
        call_command("seed_inventory", stdout=StringIO())
        count = Instrument.objects.count()
        self.assertGreater(count, 12)  # enough to see pagination
        # Running again must not duplicate anything.
        call_command("seed_inventory", stdout=StringIO())
        self.assertEqual(Instrument.objects.count(), count)

    def test_seed_does_not_overwrite_edits(self):
        call_command("seed_inventory", stdout=StringIO())
        item = Instrument.objects.get(name="Arduino Uno R3")
        item.quantity_available = 1
        item.save()
        call_command("seed_inventory", stdout=StringIO())
        item.refresh_from_db()
        self.assertEqual(item.quantity_available, 1)
