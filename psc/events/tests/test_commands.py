import datetime
from io import StringIO

from django.core.management import call_command

from core.tests.base import PscTestCase
from events.models import Discipline, EventEdition, FeedbackCriterion
from events.predictions import predicted_editions


class SeedReferenceTests(PscTestCase):
    def test_creates_disciplines_and_criteria(self):
        call_command("seed_reference", stdout=StringIO())
        self.assertGreaterEqual(Discipline.objects.count(), 9)
        self.assertGreaterEqual(FeedbackCriterion.objects.count(), 4)

    def test_is_idempotent(self):
        call_command("seed_reference", stdout=StringIO())
        before = Discipline.objects.count()
        call_command("seed_reference", stdout=StringIO())
        self.assertEqual(Discipline.objects.count(), before)


class SeedHistoryTests(PscTestCase):
    def setUp(self):
        super().setUp()
        call_command("seed_reference", stdout=StringIO())

    def test_dry_run_writes_nothing(self):
        call_command("seed_history", "--dry-run", stdout=StringIO())
        self.assertFalse(EventEdition.objects.exists())

    def test_it_only_loads_the_past(self):
        call_command("seed_history", stdout=StringIO())
        years = {edition.date_start.year for edition in EventEdition.objects.all()}
        self.assertTrue(years)
        self.assertLessEqual(max(years), 2026, "L'historique ne doit contenir aucune date future.")

    def test_every_edition_states_where_its_date_comes_from(self):
        call_command("seed_history", stdout=StringIO())
        for edition in EventEdition.objects.all():
            self.assertIn("Source de la date", edition.description)

    def test_past_editions_are_confirmed_not_provisional(self):
        call_command("seed_history", stdout=StringIO())
        self.assertFalse(
            EventEdition.objects.exclude(status=EventEdition.Status.CONFIRMED).exists()
        )

    def test_running_twice_does_not_duplicate(self):
        call_command("seed_history", stdout=StringIO())
        count = EventEdition.objects.count()
        call_command("seed_history", stdout=StringIO())
        self.assertEqual(EventEdition.objects.count(), count)

    def test_the_year_after_is_derived_and_never_stored(self):
        call_command("seed_history", stdout=StringIO())
        last = max(edition.date_start.year for edition in EventEdition.objects.all())
        self.assertEqual(EventEdition.objects.filter(date_start__year=last + 1).count(), 0)
        self.assertTrue(predicted_editions(last + 1))

    def test_purge_future_clears_anything_dated_after_the_history(self):
        self.make_edition(
            event=self.make_event("Course fantôme"), start=datetime.date(2030, 5, 1)
        )
        call_command("seed_history", "--purge-future", stdout=StringIO())
        self.assertFalse(EventEdition.all_objects.filter(date_start__year=2030).exists())

    def test_refuses_to_run_before_the_reference_data(self):
        Discipline.objects.all().delete()
        err = StringIO()
        call_command("seed_history", stdout=StringIO(), stderr=err)
        self.assertIn("seed_reference", err.getvalue())
        self.assertFalse(EventEdition.objects.exists())


class LookbackTests(PscTestCase):
    """L'historique sert sur plusieurs années, pas seulement la précédente."""

    def test_a_race_that_skipped_a_year_is_still_expected(self):
        event = self.make_event("Course intermittente")
        self.make_edition(event=event, start=datetime.date(2025, 6, 15))
        predictions = predicted_editions(2027)
        self.assertEqual(len(predictions), 1)
        self.assertEqual(predictions[0].source.date_start.year, 2025)

    def test_the_most_recent_edition_wins(self):
        event = self.make_event("Course régulière")
        self.make_edition(event=event, start=datetime.date(2024, 6, 16))
        self.make_edition(event=event, start=datetime.date(2026, 6, 14))
        predictions = predicted_editions(2027)
        self.assertEqual(predictions[0].source.date_start.year, 2026)

    def test_nothing_older_than_the_window(self):
        event = self.make_event("Course oubliée")
        self.make_edition(event=event, start=datetime.date(2020, 6, 14))
        self.assertEqual(predicted_editions(2027), [])

    def test_the_window_is_adjustable(self):
        event = self.make_event("Course oubliée")
        self.make_edition(event=event, start=datetime.date(2020, 6, 14))
        self.assertEqual(len(predicted_editions(2027, lookback=10)), 1)
