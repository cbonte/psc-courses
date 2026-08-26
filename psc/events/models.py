import datetime

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from core.models import AliveManager, SoftDeleteModel, SoftDeleteQuerySet, TimestampedModel


class Discipline(TimestampedModel):
    """Une discipline : triathlon, course à pied, natation...

    Les identifiants reprennent ceux des pastilles historiques du club (tri,
    run, swim, cyclo...), et la couleur est portée par la donnée plutôt que par
    une classe CSS figée.
    """

    slug = models.SlugField("identifiant", max_length=32, unique=True)
    label = models.CharField("libellé", max_length=64)
    color = models.CharField(
        "couleur",
        max_length=7,
        default="#6c757d",
        help_text="Code hexadécimal, par exemple #3399cc.",
    )
    position = models.PositiveSmallIntegerField("ordre d'affichage", default=100)

    class Meta:
        verbose_name = "discipline"
        verbose_name_plural = "disciplines"
        ordering = ["position", "label"]

    def __str__(self):
        return self.label


class EventQuerySet(SoftDeleteQuerySet):
    def search(self, terms):
        terms = (terms or "").strip()
        if not terms:
            return self
        return self.filter(Q(name__icontains=terms) | Q(city__icontains=terms))


class Event(SoftDeleteModel, TimestampedModel):
    """Une course, indépendamment de l'année : « Triathlon de Deauville »."""

    discipline = models.ForeignKey(
        Discipline,
        on_delete=models.PROTECT,
        related_name="events",
        verbose_name="discipline",
    )
    name = models.CharField("nom", max_length=200)
    slug = models.SlugField("identifiant", max_length=220, unique=True, blank=True)
    city = models.CharField("ville", max_length=120, blank=True)
    department = models.CharField(
        "département", max_length=8, blank=True, help_text="Code, par exemple 75 ou 2A."
    )
    website = models.URLField("site officiel", max_length=300, blank=True)
    description = models.TextField("description", blank=True)

    objects = AliveManager.from_queryset(EventQuerySet)()
    all_objects = models.Manager.from_queryset(EventQuerySet)()

    class Meta:
        base_manager_name = "all_objects"
        verbose_name = "course"
        verbose_name_plural = "courses"
        ordering = ["name"]
        indexes = [models.Index(fields=["name"], name="event_name_idx")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.name)[:200] or "course"
        candidate, suffix = base, 2
        taken = Event.objects.exclude(pk=self.pk)
        while taken.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def get_absolute_url(self):
        return reverse("events:event_detail", args=[self.slug])

    @property
    def location(self):
        if self.city and self.department:
            return f"{self.city} ({self.department})"
        return self.city or self.department or ""


class EditionQuerySet(SoftDeleteQuerySet):
    def visible(self):
        return self.exclude(status=EventEdition.Status.CANCELED).filter(
            event__deleted_at__isnull=True
        )

    def upcoming(self, today=None):
        return self.filter(date_end__gte=today or timezone.localdate())

    def past(self, today=None):
        return self.filter(date_end__lt=today or timezone.localdate())

    def for_year(self, year):
        return self.filter(date_start__year=year)

    def with_details(self):
        return self.select_related("event", "event__discipline").annotate(
            participation_count=Count(
                "participations",
                filter=Q(participations__status=Participation.Status.REGISTERED),
                distinct=True,
            ),
            feedback_count=Count("feedbacks", distinct=True),
        )


class EventEdition(SoftDeleteModel, TimestampedModel):
    """L'édition d'une année donnée : dates, statut, formats proposés."""

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmée"
        PROVISIONAL = "provisional", "À confirmer"
        CANCELED = "canceled", "Annulée"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="editions", verbose_name="course"
    )
    date_start = models.DateField("date de début")
    date_end = models.DateField("date de fin")
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.CONFIRMED
    )
    description = models.TextField("description", blank=True)
    registration_url = models.URLField("lien d'inscription", max_length=300, blank=True)

    objects = AliveManager.from_queryset(EditionQuerySet)()
    all_objects = models.Manager.from_queryset(EditionQuerySet)()

    class Meta:
        base_manager_name = "all_objects"
        verbose_name = "édition"
        verbose_name_plural = "éditions"
        ordering = ["date_start", "event__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "date_start"],
                name="edition_unique_event_date",
                violation_error_message="Cette course a déjà une édition à cette date.",
            ),
            models.CheckConstraint(
                condition=Q(date_end__gte=models.F("date_start")),
                name="edition_dates_ordered",
                violation_error_message="La date de fin ne peut pas précéder la date de début.",
            ),
        ]
        indexes = [
            models.Index(fields=["date_start"], name="edition_date_start_idx"),
            models.Index(fields=["status", "date_start"], name="edition_status_date_idx"),
        ]

    def __str__(self):
        return f"{self.event.name} {self.year}"

    def get_absolute_url(self):
        return f"{self.event.get_absolute_url()}#edition-{self.pk}"

    @property
    def year(self):
        return self.date_start.year

    @property
    def is_single_day(self):
        return self.date_start == self.date_end

    @property
    def is_past(self):
        return self.date_end < timezone.localdate()

    @property
    def days_until(self):
        return (self.date_start - timezone.localdate()).days

    @property
    def is_canceled(self):
        return self.status == self.Status.CANCELED

    def average_score(self):
        result = FeedbackScore.objects.filter(feedback__edition=self).aggregate(avg=Avg("score"))
        return result["avg"]


class EventFormat(TimestampedModel):
    """Un format proposé sur une édition : « M », « Half », « 10 km »."""

    edition = models.ForeignKey(
        EventEdition, on_delete=models.CASCADE, related_name="formats", verbose_name="édition"
    )
    name = models.CharField("nom", max_length=60)
    distance = models.CharField(
        "distances",
        max_length=120,
        blank=True,
        help_text="Par exemple : 1,5 km / 40 km / 10 km.",
    )
    description = models.TextField("description", blank=True)
    position = models.PositiveSmallIntegerField("ordre d'affichage", default=100)

    class Meta:
        verbose_name = "format"
        verbose_name_plural = "formats"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "name"],
                name="format_unique_per_edition",
                violation_error_message="Ce format existe déjà sur cette édition.",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.distance})" if self.distance else self.name


class Participation(TimestampedModel):
    """L'inscription d'un membre à une édition."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Inscrit"
        INTERESTED = "interested", "Intéressé"

    member = models.ForeignKey(
        "core.Member",
        on_delete=models.CASCADE,
        related_name="participations",
        verbose_name="membre",
    )
    edition = models.ForeignKey(
        EventEdition,
        on_delete=models.CASCADE,
        related_name="participations",
        verbose_name="édition",
    )
    format = models.ForeignKey(
        EventFormat,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="participations",
        verbose_name="format",
    )
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.REGISTERED
    )

    class Meta:
        verbose_name = "inscription"
        verbose_name_plural = "inscriptions"
        ordering = ["edition__date_start", "member__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "edition"],
                name="participation_unique_member_edition",
                violation_error_message="Ce membre est déjà inscrit à cette édition.",
            )
        ]
        indexes = [models.Index(fields=["member", "status"], name="participation_member_idx")]

    def __str__(self):
        return f"{self.member} → {self.edition}"


class FeedbackCriterion(TimestampedModel):
    """Un critère de notation : organisation, parcours, ravitaillement..."""

    label = models.CharField("libellé", max_length=64, unique=True)
    position = models.PositiveSmallIntegerField("ordre d'affichage", default=100)
    is_active = models.BooleanField("proposé aux membres", default=True)

    class Meta:
        verbose_name = "critère d'évaluation"
        verbose_name_plural = "critères d'évaluation"
        ordering = ["position", "label"]

    def __str__(self):
        return self.label


class Feedback(TimestampedModel):
    """L'évaluation d'une édition par un membre."""

    member = models.ForeignKey(
        "core.Member", on_delete=models.CASCADE, related_name="feedbacks", verbose_name="membre"
    )
    edition = models.ForeignKey(
        EventEdition, on_delete=models.CASCADE, related_name="feedbacks", verbose_name="édition"
    )
    comment = models.TextField("commentaire", blank=True)

    class Meta:
        verbose_name = "évaluation"
        verbose_name_plural = "évaluations"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "edition"],
                name="feedback_unique_member_edition",
                violation_error_message="Ce membre a déjà évalué cette édition.",
            )
        ]

    def __str__(self):
        return f"{self.member} sur {self.edition}"

    def average_score(self):
        scores = [score.score for score in self.scores.all()]
        return sum(scores) / len(scores) if scores else None


class FeedbackScore(TimestampedModel):
    """La note d'un critère au sein d'une évaluation."""

    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name="scores", verbose_name="évaluation"
    )
    criterion = models.ForeignKey(
        FeedbackCriterion,
        on_delete=models.PROTECT,
        related_name="scores",
        verbose_name="critère",
    )
    score = models.PositiveSmallIntegerField(
        "note", validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta:
        verbose_name = "note"
        verbose_name_plural = "notes"
        ordering = ["criterion__position"]
        constraints = [
            models.UniqueConstraint(
                fields=["feedback", "criterion"],
                name="score_unique_per_criterion",
                violation_error_message="Ce critère est déjà noté dans cette évaluation.",
            ),
            models.CheckConstraint(
                condition=Q(score__gte=1) & Q(score__lte=5),
                name="score_between_1_and_5",
                violation_error_message="La note doit être comprise entre 1 et 5.",
            ),
        ]

    def __str__(self):
        return f"{self.criterion} : {self.score}/5"


MONTH_NAMES = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def month_label(month):
    return MONTH_NAMES[month - 1]


def season_bounds(year):
    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


class PredictionDismissal(TimestampedModel):
    """« Cette course n'a pas lieu cette année. »

    Sans cela une course arrêtée resterait proposée chaque année, sans moyen de
    la faire taire autrement qu'en l'inscrivant à tort.
    """

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="dismissals", verbose_name="course"
    )
    year = models.PositiveSmallIntegerField("année")
    member = models.ForeignKey(
        "core.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="écartée par",
    )

    class Meta:
        verbose_name = "proposition écartée"
        verbose_name_plural = "propositions écartées"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "year"],
                name="dismissal_unique_event_year",
                violation_error_message="Cette proposition est déjà écartée.",
            )
        ]

    def __str__(self):
        return f"{self.event.name} écartée pour {self.year}"
