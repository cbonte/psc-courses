import datetime
import re

from django.urls import reverse

from core.models import Activity
from core.tests.base import PscTestCase
from events.models import Event, EventEdition, Feedback, Participation


class PageTests(PscTestCase):
    def test_dashboard_renders_when_the_calendar_is_empty(self):
        response = self.client.get(reverse("events:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Le calendrier est vide")

    def test_dashboard_lists_upcoming_editions(self):
        self.make_edition(event=self.make_event("Triathlon de Deauville"))
        response = self.client.get(reverse("events:dashboard"))
        self.assertContains(response, "Triathlon de Deauville")

    def test_dashboard_greets_the_declared_member(self):
        self.declare(self.make_member("Camille"))
        response = self.client.get(reverse("events:dashboard"))
        self.assertContains(response, "Bonjour Camille")

    def test_dashboard_shows_who_races_this_week(self):
        edition = self.make_edition(start=datetime.date.today() + datetime.timedelta(days=3))
        member = self.make_member("Noa")
        Participation.objects.create(member=member, edition=edition)
        response = self.client.get(reverse("events:dashboard"))
        self.assertContains(response, "Noa")
        self.assertContains(response, "participe")

    def test_calendar_redirects_to_the_current_year(self):
        response = self.client.get(reverse("events:calendar"))
        self.assertRedirects(
            response,
            reverse("events:calendar_year", args=[datetime.date.today().year]),
            fetch_redirect_response=False,
        )

    def test_calendar_groups_editions_by_month(self):
        self.make_edition(
            event=self.make_event("Triathlon de Paris"), start=datetime.date(2027, 6, 12)
        )
        response = self.client.get(reverse("events:calendar_year", args=[2027]))
        self.assertContains(response, "Triathlon de Paris")
        self.assertContains(response, "Juin")

    def test_event_detail_shows_editions_and_formats(self):
        event = self.make_event("Marathon de Paris", discipline=self.make_discipline("run", "Course à pied"))
        edition = self.make_edition(event=event)
        self.make_format(edition, name="42 km")
        response = self.client.get(event.get_absolute_url())
        self.assertContains(response, "Marathon de Paris")
        self.assertContains(response, "42 km")

    def test_my_events_invites_undeclared_visitors_to_identify(self):
        response = self.client.get(reverse("events:my_events"))
        self.assertContains(response, "Dites-nous qui vous êtes")

    def test_my_events_splits_past_and_upcoming(self):
        member = self.make_member()
        self.declare(member)
        future = self.make_edition(event=self.make_event("Course future"))
        past = self.make_edition(
            event=self.make_event("Course passée"),
            start=datetime.date.today() - datetime.timedelta(days=20),
        )
        Participation.objects.create(member=member, edition=future)
        Participation.objects.create(member=member, edition=past)
        response = self.client.get(reverse("events:my_events"))
        self.assertContains(response, "Course future")
        self.assertContains(response, "Course passée")


class FilterTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.tri = self.make_discipline("tri", "Triathlon")
        self.run = self.make_discipline("run", "Course à pied", "#e0a800")
        self.triathlon = self.make_edition(
            event=self.make_event("Triathlon de Vichy", discipline=self.tri),
            start=datetime.date(2027, 8, 29),
        )
        self.course = self.make_edition(
            event=self.make_event("Paris-Versailles", discipline=self.run, city="Paris"),
            start=datetime.date(2027, 9, 26),
        )
        self.url = reverse("events:calendar_year", args=[2027])

    def test_discipline_filter_keeps_only_the_selected_ones(self):
        response = self.client.get(self.url, {"discipline": "run"})
        self.assertContains(response, "Paris-Versailles")
        self.assertNotContains(response, "Triathlon de Vichy")

    def test_search_matches_name_and_city(self):
        self.assertContains(self.client.get(self.url, {"q": "vichy"}), "Triathlon de Vichy")
        self.assertContains(self.client.get(self.url, {"q": "Paris"}), "Paris-Versailles")

    def test_canceled_editions_are_hidden_unless_asked_for(self):
        self.course.status = EventEdition.Status.CANCELED
        self.course.save()
        self.assertNotContains(self.client.get(self.url), "Paris-Versailles")
        self.assertContains(self.client.get(self.url, {"statut": "canceled"}), "Paris-Versailles")

    def test_mine_filter_needs_a_declared_member(self):
        member = self.make_member()
        self.declare(member)
        Participation.objects.create(member=member, edition=self.course)
        response = self.client.get(self.url, {"mine": "1"})
        self.assertContains(response, "Paris-Versailles")
        self.assertNotContains(response, "Triathlon de Vichy")

    def test_htmx_request_returns_only_the_list_fragment(self):
        response = self.client.get(self.url, headers={"hx-request": "true"})
        self.assertNotContains(response, "<!doctype html>")
        self.assertContains(response, "calendar-results")

    def test_empty_result_explains_how_to_clear_filters(self):
        response = self.client.get(self.url, {"q": "introuvable"})
        self.assertContains(response, "Effacer les filtres")


class ParticipationTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.edition = self.make_edition()
        self.format = self.make_format(self.edition)
        self.member = self.make_member()
        self.url = reverse("events:participation", args=[self.edition.pk])

    def test_joining_without_an_identity_asks_for_one(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 409)
        self.assertIn("psc:identity-needed", response["HX-Trigger"])

    def test_joining_registers_the_member(self):
        self.declare(self.member)
        response = self.client.post(self.url, {"format": self.format.pk})
        self.assertEqual(response.status_code, 200)
        participation = Participation.objects.get(member=self.member, edition=self.edition)
        self.assertEqual(participation.format, self.format)
        self.assertEqual(participation.status, Participation.Status.REGISTERED)

    def test_joining_twice_updates_instead_of_failing(self):
        self.declare(self.member)
        self.client.post(self.url, {"format": self.format.pk})
        other = self.make_format(self.edition, name="S", distance="750 m")
        self.client.post(self.url, {"format": other.pk, "status": "interested"})
        participation = Participation.objects.get(member=self.member, edition=self.edition)
        self.assertEqual(participation.format, other)
        self.assertEqual(participation.status, Participation.Status.INTERESTED)
        self.assertEqual(Participation.objects.count(), 1)

    def test_leaving_removes_the_registration(self):
        self.declare(self.member)
        Participation.objects.create(member=self.member, edition=self.edition)
        self.client.post(self.url, {"action": "leave"})
        self.assertFalse(Participation.objects.exists())

    def test_an_unknown_status_falls_back_to_registered(self):
        self.declare(self.member)
        self.client.post(self.url, {"status": "n-importe-quoi"})
        participation = Participation.objects.get()
        self.assertEqual(participation.status, Participation.Status.REGISTERED)


class FeedbackTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.edition = self.make_edition(
            start=datetime.date.today() - datetime.timedelta(days=10)
        )
        self.member = self.make_member()
        self.criterion = self.make_criterion("Organisation")
        self.url = reverse("events:feedback", args=[self.edition.pk])

    def test_form_requires_an_identity(self):
        self.assertContains(self.client.get(self.url), "Dites-nous qui vous êtes")

    def test_form_is_shown_to_a_declared_member(self):
        self.declare(self.member)
        self.assertContains(self.client.get(self.url), "Organisation")

    def test_submitting_stores_comment_and_scores(self):
        self.declare(self.member)
        response = self.client.post(
            self.url,
            {"comment": "Très bonne organisation.", f"criterion_{self.criterion.pk}": "4"},
        )
        self.assertEqual(response.status_code, 302)
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.comment, "Très bonne organisation.")
        self.assertEqual(feedback.average_score(), 4)

    def test_an_empty_submission_is_refused(self):
        self.declare(self.member)
        response = self.client.post(self.url, {"comment": ""})
        self.assertContains(response, "Mettez au moins une note")

    def test_submitting_again_updates_the_same_review(self):
        self.declare(self.member)
        self.client.post(self.url, {"comment": "Bien", f"criterion_{self.criterion.pk}": "3"})
        self.client.post(self.url, {"comment": "Finalement très bien",
                                    f"criterion_{self.criterion.pk}": "5"})
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Feedback.objects.get().average_score(), 5)


class ExportTests(PscTestCase):
    def test_calendar_feed_is_served_as_icalendar(self):
        self.make_edition()
        response = self.client.get(reverse("events:calendar_ics"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/calendar", response["Content-Type"])
        self.assertIn("BEGIN:VCALENDAR", response.content.decode())

    def test_year_feed_only_carries_that_year(self):
        self.make_edition(
            event=self.make_event("Course 2027"), start=datetime.date(2027, 5, 1)
        )
        self.make_edition(
            event=self.make_event("Course 2028"), start=datetime.date(2028, 5, 1)
        )
        body = self.client.get(reverse("events:calendar_year_ics", args=[2027])).content.decode()
        self.assertIn("Course 2027", body)
        self.assertNotIn("Course 2028", body)

    def test_single_edition_feed(self):
        edition = self.make_edition()
        response = self.client.get(reverse("events:edition_ics", args=[edition.pk]))
        self.assertIn(f"UID:edition-{edition.pk}", response.content.decode())


class StatsTests(PscTestCase):
    def test_stats_return_twelve_months_per_discipline(self):
        edition = self.make_edition(start=datetime.date(2027, 3, 5))
        Participation.objects.create(member=self.make_member(), edition=edition)
        payload = self.client.get(reverse("events:stats_json"), {"year": 2027}).json()
        self.assertEqual(len(payload["labels"]), 12)
        self.assertEqual(len(payload["datasets"]), 1)
        dataset = payload["datasets"][0]
        self.assertEqual(dataset["label"], "Triathlon")
        self.assertEqual(dataset["data"][2], 1)
        self.assertEqual(sum(dataset["data"]), 1)

    def test_stats_are_empty_without_participation(self):
        payload = self.client.get(reverse("events:stats_json"), {"year": 2027}).json()
        self.assertEqual(payload["datasets"], [])


class YearNavigationTests(PscTestCase):
    """Régression : la liste des années affichait une entrée par édition."""

    def setUp(self):
        super().setUp()
        event = self.make_event("Triathlon de Vichy")
        for day in (5, 12, 19):
            self.make_edition(
                event=self.make_event(f"Course du {day}"),
                start=datetime.date(2027, 6, day),
            )
        self.make_edition(event=event, start=datetime.date(2027, 8, 29))

    def _years(self, year):
        response = self.client.get(reverse("events:calendar_year", args=[year]))
        return response.context["years"]

    def test_each_year_appears_once(self):
        years = self._years(2027)
        self.assertEqual(len(years), len(set(years)), "Une année est listée plusieurs fois.")

    def test_four_editions_in_one_year_yield_one_entry(self):
        self.assertEqual(self._years(2027).count(2027), 1)

    def test_years_are_sorted_and_include_the_displayed_one(self):
        years = self._years(2026)
        self.assertEqual(years, sorted(years))
        self.assertIn(2026, years)
        self.assertIn(2027, years)

    def test_one_year_ahead_is_offered_to_prepare_the_next_season(self):
        self.assertIn(2028, self._years(2027))

    def test_the_rendered_navigation_has_no_duplicate_link(self):
        html = self.client.get(reverse("events:calendar_year", args=[2026])).content.decode()
        nav = html.split('class="psc-year-nav"')[1].split("</nav>")[0]
        links = re.findall(r">\s*(\d{4})\s*</a>", nav)
        self.assertEqual(links, sorted(set(links)), f"Navigation redondante : {links}")


class EditAccessTests(PscTestCase):
    """Il n'y a pas de rôle : tout le monde édite, partout."""

    def setUp(self):
        super().setUp()
        self.edition = self.make_edition()
        self.event = self.edition.event
        self.calendar = reverse("events:calendar_year", args=[self.edition.year])

    def test_any_visitor_sees_the_edit_action(self):
        response = self.client.get(self.calendar)
        self.assertContains(response, reverse("events:edition_edit", args=[self.edition.pk]))

    def test_any_visitor_sees_the_delete_action(self):
        response = self.client.get(self.calendar)
        self.assertContains(response, reverse("events:edition_delete", args=[self.edition.pk]))

    def test_adding_a_race_is_offered_to_everyone(self):
        response = self.client.get(self.calendar)
        self.assertContains(
            response, reverse("events:edition_create_year", args=[self.edition.year])
        )

    def test_no_page_mentions_an_administration(self):
        for url in (self.calendar, reverse("events:dashboard"), self.event.get_absolute_url()):
            self.assertNotContains(self.client.get(url), "/admin/", msg_prefix=url)

    def test_the_event_page_offers_editing_to_everyone(self):
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, reverse("events:edition_edit", args=[self.edition.pk]))
        self.assertContains(response, reverse("events:edition_delete", args=[self.edition.pk]))

    def test_the_event_page_offers_adding_an_edition(self):
        response = self.client.get(self.event.get_absolute_url())
        self.assertContains(response, reverse("events:edition_create"))

    def test_the_club_screens_are_reachable_from_every_page(self):
        self.assertContains(self.client.get(self.calendar), reverse("core:club"))


class EditionEditingTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.discipline = self.make_discipline()
        self.edition = self.make_edition()
        self.make_format(self.edition, name="M", distance="1,5 / 40 / 10 km")

    def _payload(self, **overrides):
        data = {
            "name": self.edition.event.name,
            "discipline": self.discipline.pk,
            "date_start": self.edition.date_start.isoformat(),
            "date_end": "",
            "status": "confirmed",
            "city": "Paris",
            "department": "75",
            "formats": "M | 1,5 / 40 / 10 km\nS | 750 m / 20 km / 5 km",
            "description": "",
            "registration_url": "",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_the_form_opens_prefilled(self):
        self.declare(self.member)
        response = self.client.get(reverse("events:edition_edit", args=[self.edition.pk]))
        self.assertContains(response, self.edition.event.name)
        self.assertContains(response, "1,5 / 40 / 10 km")

    def test_saving_updates_the_edition_and_returns_the_card(self):
        self.declare(self.member)
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]),
            self._payload(name="Triathlon de Vichy"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Triathlon de Vichy")
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.event.name, "Triathlon de Vichy")

    def test_formats_are_synchronised_from_the_text_area(self):
        self.declare(self.member)
        self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]), self._payload()
        )
        names = list(self.edition.formats.values_list("name", flat=True))
        self.assertEqual(sorted(names), ["M", "S"])

    def test_removing_a_line_removes_the_format(self):
        self.declare(self.member)
        self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]),
            self._payload(formats="M | 1,5 / 40 / 10 km"),
        )
        self.assertEqual(list(self.edition.formats.values_list("name", flat=True)), ["M"])

    def test_editing_without_an_identity_asks_for_one(self):
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]), self._payload()
        )
        self.assertEqual(response.status_code, 409)

    def test_an_invalid_form_comes_back_with_its_errors(self):
        self.declare(self.member)
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]), self._payload(name="")
        )
        self.assertEqual(response.status_code, 422)

    def test_two_editions_of_the_same_race_on_the_same_day_are_refused(self):
        self.declare(self.member)
        other = self.make_edition(
            event=self.make_event("Autre course"),
            start=self.edition.date_start + datetime.timedelta(days=1),
        )
        response = self.client.post(
            reverse("events:edition_edit", args=[other.pk]),
            self._payload(name=self.edition.event.name),
        )
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "déjà inscrite au calendrier", status_code=422)

    def test_creating_a_race_records_who_did_it(self):
        self.declare(self.member)
        response = self.client.post(
            reverse("events:edition_create"),
            self._payload(name="Course toute neuve", date_start="2027-05-16"),
        )
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Event.objects.filter(name="Course toute neuve").exists())
        entry = Activity.objects.first()
        self.assertEqual(entry.member, self.member)
        self.assertEqual(entry.action, Activity.Action.CREATED)

    def test_cancelling_gives_the_card_back(self):
        response = self.client.get(reverse("events:edition_card", args=[self.edition.pk]))
        self.assertContains(response, self.edition.event.name)


class SoftDeleteTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.declare(self.member)
        self.edition = self.make_edition()

    def test_deleting_hides_without_destroying(self):
        self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        self.assertFalse(EventEdition.objects.filter(pk=self.edition.pk).exists())
        self.assertTrue(EventEdition.all_objects.filter(pk=self.edition.pk).exists())

    def test_the_response_offers_to_undo_immediately(self):
        response = self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        self.assertContains(response, reverse("events:edition_restore", args=[self.edition.pk]))
        self.assertContains(response, "Annuler la suppression")

    def test_restoring_brings_it_back_to_the_calendar(self):
        self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        self.client.post(reverse("events:edition_restore", args=[self.edition.pk]))
        self.assertTrue(EventEdition.objects.filter(pk=self.edition.pk).exists())

    def test_a_deleted_edition_leaves_the_calendar(self):
        self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        response = self.client.get(reverse("events:calendar_year", args=[self.edition.year]))
        self.assertNotContains(response, self.edition.event.name)

    def test_the_trash_lists_it_with_who_and_when(self):
        self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        response = self.client.get(reverse("events:trash"))
        self.assertContains(response, self.edition.event.name)
        self.assertContains(response, self.member.first_name)

    def test_deletion_and_restoration_are_both_journalled(self):
        self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        self.client.post(reverse("events:edition_restore", args=[self.edition.pk]))
        actions = list(Activity.objects.values_list("action", flat=True))
        self.assertIn(Activity.Action.DELETED, actions)
        self.assertIn(Activity.Action.RESTORED, actions)

    def test_deleting_without_an_identity_asks_for_one(self):
        self.client.post(reverse("core:identity_clear"))
        response = self.client.post(reverse("events:edition_delete", args=[self.edition.pk]))
        self.assertEqual(response.status_code, 409)


class PredictionTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.year = datetime.date.today().year
        # Une édition l'an dernier, aucune cette année : elle doit être prédite.
        self.source = self.make_edition(
            event=self.make_event("Triathlon de Deauville"),
            start=datetime.date(self.year - 1, 6, 14),
        )
        self.make_format(self.source, name="M", distance="1,5 / 40 / 10 km")
        self.url = reverse("events:calendar_year", args=[self.year])

    def test_the_calendar_shows_what_is_expected_but_not_yet_registered(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Triathlon de Deauville")
        self.assertContains(response, "Proposition")

    def test_the_predicted_date_keeps_the_weekday(self):
        response = self.client.get(self.url)
        prediction = response.context["months"][0][1][0]
        self.assertEqual(prediction.date_start.weekday(), self.source.date_start.weekday())
        self.assertEqual(prediction.date_start.year, self.year)

    def test_a_race_already_registered_is_not_predicted_twice(self):
        self.make_edition(event=self.source.event, start=datetime.date(self.year, 6, 12))
        response = self.client.get(self.url)
        self.assertNotContains(response, "Proposition")

    def test_a_cancelled_edition_predicts_nothing(self):
        self.source.status = EventEdition.Status.CANCELED
        self.source.save()
        self.assertNotContains(self.client.get(self.url), "Proposition")

    def test_what_the_button_promises_is_what_happens(self):
        """« Confirmer » produit bien une date confirmée, sans pastille de doute."""
        self.declare(self.member)
        self.client.post(
            reverse("events:prediction_confirm", args=[self.source.pk, self.year])
        )
        created = EventEdition.objects.get(event=self.source.event, date_start__year=self.year)
        self.assertEqual(created.status, EventEdition.Status.CONFIRMED)
        response = self.client.get(reverse("events:calendar_year", args=[self.year]))
        self.assertNotContains(response, "Date à confirmer")

    def test_a_confirmed_date_can_be_downgraded_afterwards(self):
        """Se tromper reste rattrapable : le formulaire rétrograde le statut."""
        self.declare(self.member)
        self.client.post(
            reverse("events:prediction_confirm", args=[self.source.pk, self.year])
        )
        created = EventEdition.objects.get(event=self.source.event, date_start__year=self.year)
        self.client.post(
            reverse("events:edition_edit", args=[created.pk]),
            {
                "name": created.event.name,
                "discipline": created.event.discipline_id,
                "date_start": created.date_start.isoformat(),
                "date_end": "",
                "status": "provisional",
                "city": "", "department": "", "formats": "",
                "description": "", "registration_url": "", "website": "",
            },
        )
        created.refresh_from_db()
        self.assertEqual(created.status, EventEdition.Status.PROVISIONAL)

    def test_confirming_creates_the_edition_with_its_formats(self):
        self.declare(self.member)
        response = self.client.post(
            reverse("events:prediction_confirm", args=[self.source.pk, self.year])
        )
        self.assertEqual(response.status_code, 200)
        created = EventEdition.objects.get(event=self.source.event, date_start__year=self.year)
        self.assertEqual(created.status, EventEdition.Status.CONFIRMED)
        self.assertEqual(list(created.formats.values_list("name", flat=True)), ["M"])

    def test_confirming_needs_an_identity(self):
        response = self.client.post(
            reverse("events:prediction_confirm", args=[self.source.pk, self.year])
        )
        self.assertEqual(response.status_code, 409)

    def test_confirming_twice_does_not_duplicate(self):
        self.declare(self.member)
        url = reverse("events:prediction_confirm", args=[self.source.pk, self.year])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(
            EventEdition.objects.filter(
                event=self.source.event, date_start__year=self.year
            ).count(),
            1,
        )

    def test_adjusting_offers_a_form_on_the_predicted_date(self):
        self.declare(self.member)
        response = self.client.get(
            reverse("events:prediction_adjust", args=[self.source.pk, self.year])
        )
        self.assertContains(response, "Triathlon de Deauville")
        self.assertContains(response, str(self.year))

    def test_predictions_are_hidden_when_filtering_on_my_own_races(self):
        self.declare(self.member)
        self.assertNotContains(self.client.get(self.url, {"mine": "1"}), "Proposition")

    def test_predictions_follow_the_discipline_filter(self):
        response = self.client.get(self.url, {"discipline": "run"})
        self.assertNotContains(response, "Proposition")


class ReturnToTests(PscTestCase):
    """Une action lancée depuis la fiche d'une course y ramène."""

    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.declare(self.member)
        self.edition = self.make_edition()
        self.detail = self.edition.event.get_absolute_url()
        self.discipline = self.edition.event.discipline

    def _payload(self, **extra):
        data = {
            "name": self.edition.event.name,
            "discipline": self.discipline.pk,
            "date_start": self.edition.date_start.isoformat(),
            "date_end": "",
            "status": "confirmed",
            "city": "",
            "department": "",
            "formats": "",
            "description": "Corrigée depuis la fiche.",
            "registration_url": "",
            "website": "",
        }
        data.update(extra)
        return data

    def test_editing_from_the_event_page_returns_there(self):
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]),
            self._payload(return_to=self.detail),
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], self.detail)

    def test_editing_from_the_calendar_returns_the_card(self):
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]), self._payload()
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.edition.event.name)

    def test_an_outside_return_address_is_ignored(self):
        response = self.client.post(
            reverse("events:edition_edit", args=[self.edition.pk]),
            self._payload(return_to="https://ailleurs.example.org/"),
        )
        self.assertEqual(response.status_code, 200)

    def test_deleting_from_the_event_page_returns_there(self):
        response = self.client.post(
            reverse("events:edition_delete", args=[self.edition.pk]),
            {"return_to": self.detail},
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], self.detail)
