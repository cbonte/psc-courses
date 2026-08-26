"""Report d'une édition d'une année sur l'autre.

Une course annuelle ne tombe pas à la même date, mais au même moment de la
semaine : le premier dimanche d'octobre, le samedi de l'Ascension. Reporter une
date, c'est donc garder le jour de la semaine et non le quantième.
"""

import datetime
from dataclasses import dataclass

from events.models import Event, EventEdition, PredictionDismissal


def predict_date(day, year):
    """Reporte `day` sur `year` en conservant son jour de la semaine.

    Deux cas limites méritent l'attention :

    * une date déjà tombée sur le bon jour de la semaine ne doit pas bouger,
      et non se décaler d'une semaine entière ;
    * un 29 février reporté sur une année non bissextile n'existe pas, et se
      rabat sur le 28.
    """
    try:
        anchor = day.replace(year=year)
    except ValueError:
        anchor = day.replace(year=year, day=28)

    gap = (day.weekday() - anchor.weekday()) % 7
    if gap == 0:
        shift = 0
    elif gap <= 3:
        shift = gap
    else:
        shift = gap - 7
    return anchor + datetime.timedelta(days=shift)


@dataclass
class PredictedEdition:
    """Une édition probable, jamais enregistrée en base.

    Se comporte comme une EventEdition pour les gabarits, mais n'a pas de clé
    primaire : elle n'existe que le temps de l'affichage, jusqu'à ce qu'un
    membre la confirme.
    """

    event: Event
    date_start: datetime.date
    date_end: datetime.date
    source: EventEdition

    is_prediction = True
    status = EventEdition.Status.PROVISIONAL
    description = ""
    registration_url = ""
    participation_count = 0
    feedback_count = 0
    pk = None

    @property
    def year(self):
        return self.date_start.year

    @property
    def is_canceled(self):
        return False

    @property
    def is_past(self):
        return self.date_end < datetime.date.today()

    @property
    def days_until(self):
        return (self.date_start - datetime.date.today()).days

    @property
    def formats(self):
        return self.source.formats

    def get_absolute_url(self):
        return self.event.get_absolute_url()


# Profondeur d'historique consultée pour deviner l'année à venir. Trois ans
# laissent passer une année blanche : une course sautée une fois reste
# proposée, alors qu'un seul an d'historique la ferait disparaître.
DEFAULT_LOOKBACK = 3


def predicted_editions(year, lookback=DEFAULT_LOOKBACK):
    """Les courses attendues cette année et pas encore inscrites.

    Pour chaque course, on part de son édition la plus récente dans les
    `lookback` années précédentes. Une édition annulée ne prédit rien : une
    course annulée l'an dernier n'annonce pas une course cette année.
    """
    already_planned = set(
        EventEdition.objects.filter(date_start__year=year).values_list("event_id", flat=True)
    )
    already_planned |= set(
        PredictionDismissal.objects.filter(year=year).values_list("event_id", flat=True)
    )
    history = (
        EventEdition.objects.filter(
            date_start__year__gte=year - lookback, date_start__year__lt=year
        )
        .exclude(status=EventEdition.Status.CANCELED)
        .exclude(event_id__in=already_planned)
        .select_related("event", "event__discipline")
        .prefetch_related("formats")
        .order_by("event_id", "-date_start")
    )

    predictions = []
    seen = set()
    for edition in history:
        # L'ordre garantit que la première rencontrée est la plus récente.
        if edition.event_id in seen:
            continue
        seen.add(edition.event_id)
        start = predict_date(edition.date_start, year)
        span = edition.date_end - edition.date_start
        predictions.append(
            PredictedEdition(
                event=edition.event, date_start=start, date_end=start + span, source=edition
            )
        )
    predictions.sort(key=lambda item: (item.date_start, item.event.name))
    return predictions
