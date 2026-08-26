from django.test import override_settings
from django.urls import reverse

from core.tests.base import ACCESS_PASSWORD, PscTestCase


class SharedAccessTests(PscTestCase):
    def test_visitor_without_password_is_redirected(self):
        self.revoke_access()
        response = self.client.get(reverse("events:dashboard"))
        self.assertRedirects(response, reverse("core:access"))

    def test_deep_link_is_kept_across_the_gate(self):
        self.revoke_access()
        target = reverse("events:my_events")
        response = self.client.get(target)
        self.assertIn(f"suite={target}", response["Location"])

    def test_correct_password_opens_the_site(self):
        self.revoke_access()
        response = self.client.post(
            reverse("core:access"), {"password": ACCESS_PASSWORD}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("events:dashboard")).status_code, 200)

    def test_wrong_password_is_rejected(self):
        self.revoke_access()
        response = self.client.post(reverse("core:access"), {"password": "au-hasard"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mot de passe incorrect")

    @override_settings(PSC_ACCESS_MAX_ATTEMPTS=3)
    def test_repeated_failures_lock_the_form(self):
        self.revoke_access()
        for _ in range(3):
            self.client.post(reverse("core:access"), {"password": "non"})
        response = self.client.post(reverse("core:access"), {"password": ACCESS_PASSWORD})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Trop de tentatives", status_code=429)

    def test_the_club_screens_are_behind_the_gate_too(self):
        self.revoke_access()
        for name in ("core:club", "core:disciplines", "core:members", "core:activity"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertTrue(
                response["Location"].startswith(reverse("core:access")),
                f"{name} : redirigé vers {response['Location']}",
            )

    def test_there_is_no_django_admin_left(self):
        self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_healthcheck_is_public(self):
        self.revoke_access()
        self.assertEqual(self.client.get(reverse("core:healthz")).status_code, 200)
