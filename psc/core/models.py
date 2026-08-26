from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class AliveManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Manager par défaut : ne voit que ce qui n'est pas supprimé."""

    def get_queryset(self):
        return super().get_queryset().alive()


class SoftDeleteModel(models.Model):
    """Rien n'est effacé : tout se restaure.

    L'édition des épreuves est ouverte à tous les membres. La contrepartie
    n'est pas de restreindre le geste, mais de le rendre réversible.
    """

    deleted_at = models.DateTimeField("supprimé le", null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        "core.Member",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="supprimé par",
    )

    class Meta:
        abstract = True

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self, member=None):
        self.deleted_at = timezone.now()
        self.deleted_by = member
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])


class MemberQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def search(self, terms):
        terms = (terms or "").strip()
        if not terms:
            return self
        query = models.Q()
        for word in terms.split():
            query &= models.Q(first_name__icontains=word) | models.Q(last_name__icontains=word)
        return self.filter(query)


class Member(TimestampedModel):
    """Un membre du club.

    Ce n'est pas un compte : il n'y a ni mot de passe ni connexion individuelle.
    Le visiteur déclare qui il est, et son navigateur s'en souvient.

    La limite est assumée : quiconque connaît le mot de passe du club peut se
    déclarer comme n'importe quel membre. Ce qui protège n'est donc pas une
    permission mais la réversibilité, suppression douce et journal.
    """

    first_name = models.CharField("prénom", max_length=80)
    last_name = models.CharField("nom", max_length=80, blank=True)
    is_active = models.BooleanField(
        "membre actif",
        default=True,
        help_text="Décocher plutôt que supprimer : les inscriptions passées sont conservées.",
    )

    objects = MemberQuerySet.as_manager()

    class Meta:
        verbose_name = "membre"
        verbose_name_plural = "membres"
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                Lower("first_name"),
                Lower("last_name"),
                name="member_unique_name_ci",
                violation_error_message="Ce membre existe déjà.",
            )
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def initials(self):
        parts = [self.first_name, self.last_name]
        return "".join(part[0].upper() for part in parts if part)


class News(SoftDeleteModel, TimestampedModel):
    """Une annonce affichée sur la page d'accueil."""

    title = models.CharField("titre", max_length=160)
    body = models.TextField(
        "message",
        help_text="Texte simple. Les sauts de ligne sont conservés, le HTML est échappé.",
    )
    published_at = models.DateTimeField("publiée le")
    is_published = models.BooleanField("visible", default=True)

    objects = AliveManager()
    all_objects = models.Manager()  # noqa: DJ012 -- managers après les champs, volontairement

    class Meta:
        base_manager_name = "all_objects"
        verbose_name = "annonce"
        verbose_name_plural = "annonces"
        ordering = ["-published_at"]
        indexes = [models.Index(fields=["-published_at"], name="news_published_idx")]

    def __str__(self):
        return self.title


class Activity(models.Model):
    """Qui a fait quoi, et quand.

    L'édition est sans restriction : ce journal est la seule chose qui permet
    de comprendre après coup ce qui s'est passé sur une épreuve.
    """

    class Action(models.TextChoices):
        CREATED = "created", "création"
        UPDATED = "updated", "modification"
        DELETED = "deleted", "suppression"
        RESTORED = "restored", "restauration"

    member = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name="membre",
    )
    action = models.CharField("action", max_length=16, choices=Action.choices)
    label = models.CharField("objet", max_length=220)
    url = models.CharField("lien", max_length=300, blank=True)
    detail = models.CharField("détail", max_length=300, blank=True)
    created_at = models.DateTimeField("le", auto_now_add=True)

    class Meta:
        verbose_name = "activité"
        verbose_name_plural = "activités"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="activity_recent_idx")]

    def __str__(self):
        who = self.member.full_name if self.member else "quelqu'un"
        return f"{who} : {self.get_action_display()} de {self.label}"

    @classmethod
    def log(cls, member, action, target, detail=""):
        return cls.objects.create(
            member=member,
            action=action,
            label=str(target)[:220],
            url=target.get_absolute_url() if hasattr(target, "get_absolute_url") else "",
            detail=detail[:300],
        )
