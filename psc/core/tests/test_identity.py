from django.urls import reverse

from core.middleware import MEMBER_SESSION_KEY
from core.models import Member
from core.tests.base import PscTestCase


class IdentityTests(PscTestCase):
    def test_picker_lists_active_members_only(self):
        self.make_member("Camille", "Durand")
        Member.objects.create(first_name="Ancien", last_name="Membre", is_active=False)
        response = self.client.get(reverse("core:identity_picker"))
        self.assertContains(response, "Camille")
        self.assertNotContains(response, "Ancien")

    def test_search_filters_on_both_names(self):
        self.make_member("Camille", "Durand")
        self.make_member("Alex", "Martin")
        response = self.client.get(reverse("core:identity_search"), {"q": "mart"})
        self.assertContains(response, "Alex")
        self.assertNotContains(response, "Camille")

    def test_choosing_a_member_stores_it_in_session(self):
        member = self.make_member()
        response = self.client.post(reverse("core:identity_set"), {"member": member.pk})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.session[MEMBER_SESSION_KEY], member.pk)

    def test_creating_a_member_adopts_it(self):
        response = self.client.post(
            reverse("core:identity_create"), {"first_name": "Noa", "last_name": "Leroy"}
        )
        self.assertEqual(response.status_code, 204)
        member = Member.objects.get(first_name="Noa")
        self.assertEqual(self.client.session[MEMBER_SESSION_KEY], member.pk)

    def test_creating_an_existing_member_reuses_it_instead_of_duplicating(self):
        existing = self.make_member("Noa", "Leroy")
        self.client.post(
            reverse("core:identity_create"), {"first_name": "noa", "last_name": "LEROY"}
        )
        self.assertEqual(Member.objects.count(), 1)
        self.assertEqual(self.client.session[MEMBER_SESSION_KEY], existing.pk)

    def test_restore_replays_the_browser_memory(self):
        member = self.make_member()
        response = self.client.post(reverse("core:identity_restore"), {"member": member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restored"])
        self.assertEqual(self.client.session[MEMBER_SESSION_KEY], member.pk)

    def test_restore_of_a_deactivated_member_fails_cleanly(self):
        member = self.make_member()
        member.is_active = False
        member.save()
        response = self.client.post(reverse("core:identity_restore"), {"member": member.pk})
        self.assertEqual(response.status_code, 404)

    def test_clearing_forgets_the_identity(self):
        member = self.make_member()
        self.declare(member)
        self.client.post(reverse("core:identity_clear"))
        self.assertNotIn(MEMBER_SESSION_KEY, self.client.session)

    def test_deactivated_member_is_dropped_from_session(self):
        member = self.make_member()
        self.declare(member)
        member.is_active = False
        member.save()
        response = self.client.get(reverse("events:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(MEMBER_SESSION_KEY, self.client.session)
