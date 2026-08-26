import datetime

from core.tests.base import PscTestCase
from events.icalendar import build_calendar, escape, fold
from events.models import EventEdition


class IcalendarTests(PscTestCase):
    def test_special_characters_are_escaped(self):
        self.assertEqual(escape("Paris; 10, rue\nB"), r"Paris\; 10\, rue\nB")

    def test_long_lines_are_folded_with_a_leading_space(self):
        folded = fold("SUMMARY:" + "a" * 200)
        self.assertIn("\r\n ", folded)
        for line in folded.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 76)

    def test_calendar_carries_one_event_per_edition(self):
        edition = self.make_edition(start=datetime.date(2027, 6, 12))
        body = build_calendar([edition], name="Test")
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn(f"UID:edition-{edition.pk}@paris-sport-club", body)
        self.assertIn("DTSTART;VALUE=DATE:20270612", body)
        # DTEND est exclusif : le lendemain de la fin.
        self.assertIn("DTEND;VALUE=DATE:20270613", body)
        self.assertIn("STATUS:CONFIRMED", body)

    def test_provisional_and_canceled_editions_are_marked(self):
        provisional = self.make_edition(status=EventEdition.Status.PROVISIONAL)
        body = build_calendar([provisional], name="Test")
        self.assertIn("STATUS:TENTATIVE", body)
        self.assertIn("[à confirmer]", body)

        canceled = self.make_edition(
            event=self.make_event("Course annulée"), status=EventEdition.Status.CANCELED
        )
        self.assertIn("STATUS:CANCELLED", build_calendar([canceled], name="Test"))
