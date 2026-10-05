from django.test import TestCase
from django.urls import reverse

from inventory.models import Category, Instrument
from users.models import User

from . import services
from .models import IssueRequest, UsageLog


def make_instrument(name, available=5, total=5, **kwargs):
    category, _ = Category.objects.get_or_create(name="Sensors")
    return Instrument.objects.create(
        name=name, category=category, quantity_available=available, quantity_total=total, **kwargs
    )


class WorkflowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user("s@stu.xim.edu.in")
        self.staff = User.objects.create_user("la@xim.edu.in", role=User.Role.LAB_ASSISTANT)
        self.esp = make_instrument("ESP32", available=10, total=10)
        self.dht = make_instrument("DHT22", available=4, total=4)

    def new_request(self, items=None, user=None, days=14):
        if items is None:
            items = [(self.esp, 3), (self.dht, 2)]
        return services.create_request(user or self.student, items, "Weather station for class", "", days)

    def stock(self, instrument):
        instrument.refresh_from_db()
        return instrument.quantity_available

    def test_create_request_saves_items_and_logs(self):
        req = self.new_request()
        self.assertEqual(req.status, IssueRequest.Status.PENDING)
        self.assertEqual(req.items.count(), 2)
        self.assertEqual(UsageLog.objects.filter(action="requested").count(), 2)
        self.assertEqual(self.stock(self.esp), 10)  # asking does not take stock

    def test_full_cycle_updates_stock_and_logs_each_step(self):
        req = self.new_request()
        services.approve(req, self.staff)
        self.assertEqual(self.stock(self.esp), 10)  # approving does not reserve
        req.refresh_from_db()
        self.assertEqual(req.reviewed_by, self.staff)
        self.assertIsNotNone(req.reviewed_at)

        services.issue(req, self.staff)
        self.assertEqual(self.stock(self.esp), 7)
        self.assertEqual(self.stock(self.dht), 2)
        req.refresh_from_db()
        self.assertEqual(req.status, IssueRequest.Status.ISSUED)
        self.assertEqual((req.due_at - req.issued_at).days, 14)

        services.mark_returned(req, self.staff)
        self.assertEqual(self.stock(self.esp), 10)
        self.assertEqual(self.stock(self.dht), 4)
        req.refresh_from_db()
        self.assertEqual(req.status, IssueRequest.Status.RETURNED)
        self.assertIsNotNone(req.returned_at)

        # 2 items x 4 steps (requested, approved, issued, returned)
        self.assertEqual(UsageLog.objects.count(), 8)

    def test_reject_logs_and_never_touches_stock(self):
        req = self.new_request()
        services.reject(req, self.staff, "Not needed for that course")
        req.refresh_from_db()
        self.assertEqual(req.status, IssueRequest.Status.REJECTED)
        self.assertEqual(self.stock(self.esp), 10)
        self.assertTrue(UsageLog.objects.filter(action="rejected", note__contains="Not needed").exists())

    def test_steps_must_follow_the_order(self):
        req = self.new_request()
        for step in (services.issue, services.mark_returned):
            with self.subTest(step=step.__name__), self.assertRaises(services.RequestError):
                step(req, self.staff)  # still pending
        services.approve(req, self.staff)
        with self.assertRaises(services.RequestError):
            services.approve(req, self.staff)  # cannot approve twice
        services.issue(req, self.staff)
        with self.assertRaises(services.RequestError):
            services.issue(req, self.staff)  # cannot issue twice
        services.mark_returned(req, self.staff)
        with self.assertRaises(services.RequestError):
            services.mark_returned(req, self.staff)  # cannot return twice
        self.assertEqual(self.stock(self.esp), 10)  # stock correct after all that

    def test_issue_is_all_or_nothing_when_one_item_runs_short(self):
        other = User.objects.create_user("o@stu.xim.edu.in")
        mine = self.new_request([(self.esp, 2), (self.dht, 3)])
        theirs = self.new_request([(self.dht, 3)], user=other)
        services.approve(mine, self.staff)
        services.approve(theirs, self.staff)
        services.issue(theirs, self.staff)  # leaves only 1 DHT22
        with self.assertRaises(services.RequestError):
            services.issue(mine, self.staff)
        self.assertEqual(self.stock(self.esp), 10)  # the ESP32s were not taken either
        self.assertEqual(self.stock(self.dht), 1)
        mine.refresh_from_db()
        self.assertEqual(mine.status, IssueRequest.Status.APPROVED)

    def test_return_never_exceeds_total(self):
        req = self.new_request([(self.dht, 2)])
        services.approve(req, self.staff)
        services.issue(req, self.staff)
        Instrument.objects.filter(pk=self.dht.pk).update(quantity_available=4)  # miscount
        services.mark_returned(req, self.staff)
        self.assertEqual(self.stock(self.dht), 4)

    def test_request_rules(self):
        with self.assertRaises(services.RequestError):
            self.new_request([(self.esp, 11)])  # more than available
        with self.assertRaises(services.RequestError):
            self.new_request([])  # empty basket
        with self.assertRaises(services.RequestError):
            self.new_request(days=31)  # too long
        printer = make_instrument("3D printer", available=1, total=1, is_bookable=True)
        broken = make_instrument("Scope", status=Instrument.Status.MAINTENANCE)
        empty = make_instrument("Pico", available=0, total=5)
        for item in (printer, broken, empty):
            with self.subTest(item=item.name), self.assertRaises(services.RequestError):
                self.new_request([(item, 1)])

    def test_failed_request_creates_nothing(self):
        with self.assertRaises(services.RequestError):
            self.new_request([(self.esp, 1), (self.dht, 99)])
        self.assertEqual(IssueRequest.objects.count(), 0)
        self.assertEqual(UsageLog.objects.count(), 0)

    def test_one_open_request_per_item(self):
        self.new_request([(self.esp, 1)])
        with self.assertRaises(services.RequestError):
            self.new_request([(self.esp, 1)])
        # another student can still ask for it
        self.new_request([(self.esp, 1)], user=User.objects.create_user("o@stu.xim.edu.in"))


class StudentPagesTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user("s@stu.xim.edu.in")
        self.esp = make_instrument("ESP32", available=10, total=10)
        self.dht = make_instrument("DHT22", available=4, total=4)
        self.client.force_login(self.student)

    def add(self, instrument, quantity=1):
        return self.client.post(reverse("issue_requests:basket_add", args=[instrument.pk]), {"quantity": quantity})

    def submit(self, **overrides):
        data = {"purpose": "Weather station for class", "course_or_project": "", "duration_days": 14, "agree": "on"}
        data.update(overrides)
        return self.client.post(reverse("issue_requests:basket"), data)

    def test_login_required(self):
        self.client.logout()
        for name in ("issue_requests:list", "issue_requests:basket"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_basket_add_update_remove(self):
        self.add(self.esp, 3)
        self.add(self.dht, 1)
        self.client.post(reverse("issue_requests:basket_update", args=[self.esp.pk]), {"quantity": 5})
        self.client.post(reverse("issue_requests:basket_remove", args=[self.dht.pk]))
        response = self.client.get(reverse("issue_requests:basket"))
        self.assertEqual([(i.name, q) for i, q in response.context["items"]], [("ESP32", 5)])

    def test_cannot_add_more_than_available(self):
        response = self.add(self.dht, 9)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.client.get(reverse("issue_requests:basket")).context["items"]), 0)

    def test_submit_creates_one_request_with_all_items_and_empties_basket(self):
        self.add(self.esp, 3)
        self.add(self.dht, 2)
        response = self.submit(course_or_project="IoT 101")
        self.assertRedirects(response, reverse("issue_requests:list"))
        req = IssueRequest.objects.get()
        self.assertEqual(req.user, self.student)
        self.assertEqual(req.duration_days, 14)
        self.assertEqual(req.items.count(), 2)
        self.assertEqual(len(self.client.get(reverse("issue_requests:basket")).context["items"]), 0)

    def test_form_validation(self):
        self.add(self.esp, 1)
        for bad in ({"duration_days": 31}, {"duration_days": 0}, {"purpose": "too short"}, {"agree": ""}):
            with self.subTest(bad=bad):
                self.submit(**bad)
                self.assertEqual(IssueRequest.objects.count(), 0)

    def test_my_requests_shows_only_my_own(self):
        other = User.objects.create_user("o@stu.xim.edu.in")
        services.create_request(other, [(self.esp, 1)], "Someone else's project", "", 7)
        services.create_request(self.student, [(self.dht, 1)], "My own project here", "", 7)
        response = self.client.get(reverse("issue_requests:list"))
        shown = list(response.context["page"].object_list)
        self.assertEqual([r.user for r in shown], [self.student])

    def test_detail_page_shows_why_a_request_is_blocked(self):
        out = make_instrument("Pico", available=0, total=5)
        response = self.client.get(reverse("inventory:detail", args=[out.pk]))
        self.assertContains(response, "out of stock")
        self.assertNotContains(response, 'name="quantity"')
        response = self.client.get(reverse("inventory:detail", args=[self.esp.pk]))
        self.assertContains(response, 'name="quantity"')

    def test_navbar_counts(self):
        self.add(self.esp, 1)
        response = self.client.get(reverse("inventory:list"))
        self.assertEqual(response.context["basket_count"], 1)
        self.assertEqual(response.context["open_request_count"], 0)


class StaffAdminTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user("s@stu.xim.edu.in")
        self.assistant = User.objects.create_user("la@xim.edu.in", role=User.Role.LAB_ASSISTANT)
        self.esp = make_instrument("ESP32", available=10, total=10)
        self.req = services.create_request(self.student, [(self.esp, 4)], "Class project work", "", 10)
        self.url = reverse("admin:issue_requests_issuerequest_changelist")

    def run_action(self, action):
        return self.client.post(
            self.url, {"action": action, "_selected_action": [self.req.pk]}, follow=True
        )

    def test_student_cannot_use_the_request_admin(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_lab_assistant_runs_the_whole_flow_from_admin_actions(self):
        self.client.force_login(self.assistant)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.run_action("approve_selected")
        self.run_action("issue_selected")
        self.esp.refresh_from_db()
        self.assertEqual(self.esp.quantity_available, 6)
        self.run_action("return_selected")
        self.esp.refresh_from_db()
        self.assertEqual(self.esp.quantity_available, 10)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, IssueRequest.Status.RETURNED)

    def test_wrong_step_from_admin_is_refused_with_a_message(self):
        self.client.force_login(self.assistant)
        response = self.run_action("issue_selected")  # still pending
        self.assertContains(response, "does not apply")
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, IssueRequest.Status.PENDING)

    def test_status_cannot_be_edited_directly_or_requests_added_or_deleted(self):
        self.client.force_login(self.assistant)
        response = self.client.get(reverse("admin:issue_requests_issuerequest_change", args=[self.req.pk]))
        self.assertNotIn("status", response.context["adminform"].form.fields)
        self.assertEqual(self.client.get(reverse("admin:issue_requests_issuerequest_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:issue_requests_issuerequest_delete", args=[self.req.pk])).status_code, 403)
