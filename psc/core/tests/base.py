import datetime

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings

from core.middleware import ACCESS_SESSION_KEY, MEMBER_SESSION_KEY
from core.models import Member
from events.models import Discipline, Event, EventEdition, EventFormat, FeedbackCriterion

ACCESS_PASSWORD = "vive-le-club"
ACCESS_HASH = make_password(ACCESS_PASSWORD)


@override_settings(PSC_ACCESS_PASSWORD_HASH=ACCESS_HASH)
class PscTestCase(TestCase):
    """Base commune : le site est protégé, et l'accès est accordé par défaut."""

    def setUp(self):
        super().setUp()
        self.grant_access()

    def grant_access(self):
        session = self.client.session
        session[ACCESS_SESSION_KEY] = True
        session.save()

    def revoke_access(self):
        session = self.client.session
        session.pop(ACCESS_SESSION_KEY, None)
        session.save()

    def declare(self, member):
        session = self.client.session
        session[MEMBER_SESSION_KEY] = member.pk
        session.save()

    # Fabriques ------------------------------------------------------------

    def make_member(self, first="Camille", last="Durand"):
        return Member.objects.create(first_name=first, last_name=last)

    def make_discipline(self, slug="tri", label="Triathlon", color="#cc6666"):
        discipline, _ = Discipline.objects.get_or_create(
            slug=slug, defaults={"label": label, "color": color}
        )
        return discipline

    def make_event(self, name="Triathlon de Paris", discipline=None, **kwargs):
        discipline = discipline or self.make_discipline()
        kwargs.setdefault("city", "Paris")
        kwargs.setdefault("department", "75")
        return Event.objects.create(name=name, discipline=discipline, **kwargs)

    def make_edition(self, event=None, start=None, end=None, **kwargs):
        event = event or self.make_event()
        start = start or datetime.date.today() + datetime.timedelta(days=30)
        return EventEdition.objects.create(
            event=event, date_start=start, date_end=end or start, **kwargs
        )

    def make_format(self, edition, name="M", distance="1,5 / 40 / 10 km"):
        return EventFormat.objects.create(edition=edition, name=name, distance=distance)

    def make_criterion(self, label="Organisation"):
        return FeedbackCriterion.objects.create(label=label)
