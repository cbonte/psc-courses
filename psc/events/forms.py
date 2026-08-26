from django import forms
from django.utils.text import slugify

from core.richfields import RichTextField
from events.models import (
    Discipline,
    Event,
    EventEdition,
    EventFormat,
    Feedback,
    FeedbackCriterion,
    FeedbackScore,
)

SCORE_CHOICES = [(value, f"{value}") for value in range(1, 6)]

# Le navigateur envoie de l'ISO ; la saisie manuelle sans JavaScript peut
# arriver au format français.
ISO_AND_FRENCH = ["%Y-%m-%d", "%d/%m/%Y"]


class EditionForm(forms.Form):
    """Créer ou corriger une épreuve, en un seul formulaire.

    Volontairement à plat plutôt qu'un ModelForm sur deux modèles : le membre
    saisit « une course à une date », pas « un Event puis une EventEdition ».
    Le nom pilote tout : s'il correspond à une course connue, la discipline,
    la ville et le site sont hérités et n'ont pas à être ressaisis.
    """

    name = forms.CharField(
        label="Nom de la course",
        max_length=200,
        help_text="Sans l'année. « Triathlon de Deauville », pas « Deauville 2027 ».",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "autocomplete": "off",
                "list": "event-names",
                "placeholder": "Commencez à taper, les courses connues sont proposées",
            }
        ),
    )
    discipline = forms.ModelChoiceField(
        label="Discipline",
        queryset=Discipline.objects.all(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    # Un <input type="date"> n'accepte que l'ISO. Sans ce format explicite,
    # la localisation française rend « 25/09/2026 » et le champ reste vide.
    date_start = forms.DateField(
        label="Date",
        input_formats=ISO_AND_FRENCH,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    date_end = forms.DateField(
        label="Dernier jour",
        required=False,
        help_text="À remplir seulement si la course dure plusieurs jours.",
        input_formats=ISO_AND_FRENCH,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
    )
    status = forms.ChoiceField(
        label="Statut",
        choices=EventEdition.Status.choices,
        initial=EventEdition.Status.CONFIRMED,
        widget=forms.RadioSelect(attrs={"class": "btn-check"}),
    )
    city = forms.CharField(
        label="Ville",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    department = forms.CharField(
        label="Département",
        max_length=8,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "75"}),
    )
    formats = forms.CharField(
        label="Formats",
        required=False,
        help_text="Un par ligne. Nom, puis distances après une barre verticale : "
        "« M | 1,5 / 40 / 10 km ».",
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3, "placeholder": "M | 1,5 / 40 / 10 km"}
        ),
    )
    description = RichTextField(
        label="Description",
        rows=4,
        placeholder="Parcours, ambiance, conseils… Gras, listes et liens sont possibles.",
    )
    registration_url = forms.URLField(
        label="Lien d'inscription",
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://"}),
    )
    website = forms.URLField(
        label="Site officiel",
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(attrs={"class": "form-control", "placeholder": "https://"}),
    )

    def __init__(self, data=None, *args, edition=None, **kwargs):
        self.edition = edition
        # `data` est nommé explicitement : la vue appelle le formulaire avec
        # `request.POST or None`, donc un None positionnel. Tester la vacuité
        # de *args laissait croire à une soumission et vidait le formulaire.
        if edition is not None and data is None and "initial" not in kwargs:
            kwargs["initial"] = self.initial_from(edition)
        super().__init__(data, *args, **kwargs)

    @staticmethod
    def initial_from(edition, date_start=None):
        event = edition.event
        return {
            "name": event.name,
            "discipline": event.discipline_id,
            "date_start": date_start or edition.date_start,
            "date_end": edition.date_end if edition.date_end != edition.date_start else None,
            "status": edition.status,
            "city": event.city,
            "department": event.department,
            "description": edition.description,
            "registration_url": edition.registration_url,
            "website": event.website,
            "formats": format_lines(edition),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("date_start"), cleaned.get("date_end")
        if start and end and end < start:
            self.add_error("date_end", "Le dernier jour ne peut pas précéder la date de début.")
        if start and not end:
            cleaned["date_end"] = start

        name, date_start = cleaned.get("name"), cleaned.get("date_start")
        if name and date_start:
            clash = EventEdition.objects.filter(
                event__name__iexact=name, date_start=date_start
            ).exclude(pk=self.edition.pk if self.edition else None)
            if clash.exists():
                self.add_error(
                    "date_start", "Cette course est déjà inscrite au calendrier à cette date."
                )
        return cleaned

    def save(self, member=None):
        data = self.cleaned_data
        event = Event.all_objects.filter(name__iexact=data["name"]).first()
        if event is None:
            event = Event(name=data["name"], slug=slugify(data["name"])[:200])
        # Une course supprimée que l'on ressaisit revient d'elle-même.
        event.deleted_at = None
        event.deleted_by = None
        event.discipline = data["discipline"]
        event.city = data["city"] or event.city
        event.department = data["department"] or event.department
        event.website = data["website"] or event.website
        event.save()

        edition = self.edition or EventEdition(event=event)
        edition.event = event
        edition.date_start = data["date_start"]
        edition.date_end = data["date_end"]
        edition.status = data["status"]
        edition.description = data["description"]
        edition.registration_url = data["registration_url"]
        edition.deleted_at = None
        edition.deleted_by = None
        edition.save()

        sync_formats(edition, data["formats"])
        return edition


def format_lines(edition):
    """Les formats d'une édition, un par ligne, tels qu'on les saisit."""
    lines = []
    for entry in edition.formats.all():
        lines.append(f"{entry.name} | {entry.distance}" if entry.distance else entry.name)
    return "\n".join(lines)


def parse_formats(text):
    """« M | 1,5 / 40 / 10 km » -> (nom, distances). Les lignes vides sautent."""
    parsed = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, distance = line.partition("|")
        name = name.strip()[:60]
        if name:
            parsed.append((name, distance.strip()[:120]))
    return parsed


def sync_formats(edition, text):
    wanted = parse_formats(text)
    keep = []
    for position, (name, distance) in enumerate(wanted, start=1):
        entry, _ = EventFormat.objects.update_or_create(
            edition=edition,
            name=name,
            defaults={"distance": distance, "position": position * 10},
        )
        keep.append(entry.pk)
    edition.formats.exclude(pk__in=keep).delete()


class FeedbackForm(forms.ModelForm):
    """Un commentaire, et une note par critère actif."""

    comment = RichTextField(
        label="Commentaire",
        rows=4,
        placeholder="Organisation, parcours, ambiance… ce qui aiderait les autres "
        "membres à choisir.",
    )

    class Meta:
        model = Feedback
        fields = ["comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.criteria = list(FeedbackCriterion.objects.filter(is_active=True))
        existing = {}
        if self.instance.pk:
            existing = {score.criterion_id: score.score for score in self.instance.scores.all()}
        for criterion in self.criteria:
            self.fields[self._field_name(criterion)] = forms.TypedChoiceField(
                label=criterion.label,
                choices=[("", "-")] + SCORE_CHOICES,
                coerce=int,
                required=False,
                empty_value=None,
                initial=existing.get(criterion.pk),
                widget=forms.RadioSelect(attrs={"class": "btn-check"}),
            )

    @staticmethod
    def _field_name(criterion):
        return f"criterion_{criterion.pk}"

    def criterion_fields(self):
        for criterion in self.criteria:
            yield criterion, self[self._field_name(criterion)]

    def clean(self):
        cleaned = super().clean()
        has_score = any(cleaned.get(self._field_name(c)) for c in self.criteria)
        if not has_score and not (cleaned.get("comment") or "").strip():
            raise forms.ValidationError("Mettez au moins une note ou écrivez un commentaire.")
        return cleaned

    def save_scores(self):
        for criterion in self.criteria:
            value = self.cleaned_data.get(self._field_name(criterion))
            if value:
                FeedbackScore.objects.update_or_create(
                    feedback=self.instance, criterion=criterion, defaults={"score": value}
                )
            else:
                FeedbackScore.objects.filter(
                    feedback=self.instance, criterion=criterion
                ).delete()
