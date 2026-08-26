"""Formulaires des écrans de gestion du club.

Ils remplacent l'administration Django : mêmes objets, mêmes contrôles, mais
dans l'application, sans rôle et sans deuxième interface à apprendre.
"""

from django import forms

from core.models import Member, News
from events.models import Discipline, FeedbackCriterion

TEXT = {"class": "form-control"}
SELECT = {"class": "form-select"}


class DisciplineForm(forms.ModelForm):
    class Meta:
        model = Discipline
        fields = ["label", "slug", "color", "position"]
        widgets = {
            "label": forms.TextInput(attrs=TEXT),
            "slug": forms.TextInput(attrs={**TEXT, "placeholder": "tri"}),
            "color": forms.TextInput(attrs={"class": "form-control form-control-color",
                                            "type": "color"}),
            "position": forms.NumberInput(attrs={**TEXT, "step": 10}),
        }
        help_texts = {
            "slug": "Identifiant court, sans accent ni espace. Sert aux filtres du calendrier.",
            "position": "Plus le nombre est petit, plus la discipline apparaît tôt.",
        }


class FeedbackCriterionForm(forms.ModelForm):
    class Meta:
        model = FeedbackCriterion
        fields = ["label", "position", "is_active"]
        widgets = {
            "label": forms.TextInput(attrs=TEXT),
            "position": forms.NumberInput(attrs={**TEXT, "step": 10}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class NewsForm(forms.ModelForm):
    class Meta:
        model = News
        fields = ["title", "body", "published_at", "is_published"]
        widgets = {
            "title": forms.TextInput(attrs=TEXT),
            "body": forms.Textarea(attrs={**TEXT, "rows": 4}),
            "published_at": forms.DateTimeInput(
                attrs={**TEXT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["published_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]


class MemberEditForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["first_name", "last_name", "is_active"]
        widgets = {
            "first_name": forms.TextInput(attrs=TEXT),
            "last_name": forms.TextInput(attrs=TEXT),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
