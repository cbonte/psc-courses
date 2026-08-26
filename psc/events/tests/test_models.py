import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import Member
from core.tests.base import PscTestCase
from events.models import EventEdition, Feedback, FeedbackScore, Participation


class ConstraintTests(PscTestCase):
    def test_member_name_is_unique_regardless_of_case(self):
        Member.objects.create(first_name="Camille", last_name="Durand")
        with self.assertRaises(IntegrityError):
            Member.objects.create(first_name="camille", last_name="DURAND")

    def test_edition_dates_must_be_ordered(self):
        event = self.make_event()
        with self.assertRaises(IntegrityError):
            EventEdition.objects.create(
                event=event,
                date_start=datetime.date(2027, 6, 10),
                date_end=datetime.date(2027, 6, 9),
            )

    def test_an_event_cannot_have_two_editions_on_the_same_day(self):
        event = self.make_event()
        day = datetime.date(2027, 6, 10)
        EventEdition.objects.create(event=event, date_start=day, date_end=day)
        with self.assertRaises(IntegrityError):
            EventEdition.objects.create(event=event, date_start=day, date_end=day)

    def test_a_member_registers_only_once_per_edition(self):
        member, edition = self.make_member(), self.make_edition()
        Participation.objects.create(member=member, edition=edition)
        with self.assertRaises(IntegrityError):
            Participation.objects.create(member=member, edition=edition)

    def test_a_member_reviews_an_edition_only_once(self):
        member, edition = self.make_member(), self.make_edition()
        Feedback.objects.create(member=member, edition=edition, comment="Bien")
        with self.assertRaises(IntegrityError):
            Feedback.objects.create(member=member, edition=edition, comment="Encore")

    def test_scores_stay_between_one_and_five(self):
        feedback = Feedback.objects.create(member=self.make_member(), edition=self.make_edition())
        criterion = self.make_criterion()
        with self.assertRaises(IntegrityError):
            FeedbackScore.objects.create(feedback=feedback, criterion=criterion, score=9)

    def test_deleting_a_format_detaches_participations_without_losing_them(self):
        edition = self.make_edition()
        fmt = self.make_format(edition)
        participation = Participation.objects.create(
            member=self.make_member(), edition=edition, format=fmt
        )
        fmt.delete()
        participation.refresh_from_db()
        self.assertIsNone(participation.format)

    def test_a_discipline_in_use_cannot_be_deleted(self):
        event = self.make_event()
        with self.assertRaises(IntegrityError), transaction.atomic():
            event.discipline.delete()


class BehaviourTests(PscTestCase):
    def test_edition_knows_whether_it_is_past(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        edition = self.make_edition(start=yesterday)
        self.assertTrue(edition.is_past)
        self.assertFalse(self.make_edition(event=self.make_event("Autre course")).is_past)

    def test_average_score_is_none_without_any_note(self):
        feedback = Feedback.objects.create(member=self.make_member(), edition=self.make_edition())
        self.assertIsNone(feedback.average_score())

    def test_average_score_averages_the_criteria(self):
        feedback = Feedback.objects.create(member=self.make_member(), edition=self.make_edition())
        FeedbackScore.objects.create(
            feedback=feedback, criterion=self.make_criterion("Organisation"), score=4
        )
        FeedbackScore.objects.create(
            feedback=feedback, criterion=self.make_criterion("Parcours"), score=2
        )
        self.assertEqual(feedback.average_score(), 3)

    def test_score_validators_reject_out_of_range_values(self):
        feedback = Feedback.objects.create(member=self.make_member(), edition=self.make_edition())
        score = FeedbackScore(feedback=feedback, criterion=self.make_criterion(), score=0)
        with self.assertRaises(ValidationError):
            score.full_clean()

    def test_upcoming_excludes_finished_editions(self):
        past = self.make_edition(
            event=self.make_event("Course passée"),
            start=datetime.date.today() - datetime.timedelta(days=10),
        )
        future = self.make_edition(event=self.make_event("Course à venir"))
        upcoming = list(EventEdition.objects.upcoming())
        self.assertIn(future, upcoming)
        self.assertNotIn(past, upcoming)
