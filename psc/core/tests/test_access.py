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


class AttemptCounterTests(PscTestCase):
    """Le compteur de tentatives vit en base, pas en mémoire du processus."""

    def setUp(self):
        super().setUp()
        self.revoke_access()

    def _rows(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("select count(*) from psc_cache")
            return cursor.fetchone()[0]

    def test_the_backend_is_the_database(self):
        from django.conf import settings

        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )

    def test_a_failed_attempt_is_written_to_the_database(self):
        self.assertEqual(self._rows(), 0)
        self.client.post(reverse("core:access"), {"password": "non"})
        self.assertEqual(self._rows(), 1)

    @override_settings(PSC_ACCESS_MAX_ATTEMPTS=3)
    def test_the_count_survives_a_fresh_client(self):
        """Un nouveau client vaut une nouvelle instance : le compteur tient."""
        from django.test import Client

        for _ in range(3):
            Client().post(reverse("core:access"), {"password": "non"})
        response = Client().post(reverse("core:access"), {"password": ACCESS_PASSWORD})
        self.assertEqual(response.status_code, 429)

    def test_a_success_clears_the_counter(self):
        self.client.post(reverse("core:access"), {"password": "non"})
        self.assertEqual(self._rows(), 1)
        self.client.post(reverse("core:access"), {"password": ACCESS_PASSWORD})
        self.assertEqual(self._rows(), 0)


class DatabaseUrlTests(PscTestCase):
    """Traduction d'une DATABASE_URL, sans serveur pour l'éprouver."""

    @staticmethod
    def _parse(url):
        from psc.settings import _database_from_url

        return _database_from_url(url)

    def test_a_neon_url_is_translated(self):
        config = self._parse(
            "postgresql://user:secret@ep-x-1.eu-central-1.aws.neon.tech/pscdb?sslmode=require"
        )
        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["NAME"], "pscdb")
        self.assertEqual(config["USER"], "user")
        self.assertEqual(config["PASSWORD"], "secret")
        self.assertEqual(config["HOST"], "ep-x-1.eu-central-1.aws.neon.tech")

    def test_a_password_with_special_characters_is_decoded(self):
        """Une URL encode @ et / : les laisser tels quels casserait la connexion."""
        config = self._parse("postgresql://u:a%40b%2Fc@host/db")
        self.assertEqual(config["PASSWORD"], "a@b/c")

    def test_tls_is_required_even_when_the_url_says_nothing(self):
        self.assertEqual(self._parse("postgresql://u:p@host/db")["OPTIONS"]["sslmode"], "require")

    def test_an_explicit_sslmode_wins(self):
        config = self._parse("postgresql://u:p@host/db?sslmode=verify-full")
        self.assertEqual(config["OPTIONS"]["sslmode"], "verify-full")

    def test_the_port_is_kept_when_given(self):
        self.assertEqual(self._parse("postgresql://u:p@host:5433/db")["PORT"], "5433")

    def test_the_connection_is_reused_between_requests(self):
        self.assertGreater(self._parse("postgresql://u:p@host/db")["CONN_MAX_AGE"], 0)
        self.assertTrue(self._parse("postgresql://u:p@host/db")["CONN_HEALTH_CHECKS"])

    def test_without_the_variable_the_project_stays_on_sqlite(self):
        from django.conf import settings

        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.sqlite3")
