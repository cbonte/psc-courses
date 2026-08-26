"""Champ de formulaire pour le texte riche.

Le gabarit rend un textarea ordinaire. Le JavaScript le remplace par l'éditeur
s'il est disponible ; sans JavaScript, la saisie reste possible en texte brut.
"""

from django import forms

from core.richtext import clean


class RichTextarea(forms.Textarea):
    """Textarea que le JavaScript remplace par l'éditeur."""

    def __init__(self, attrs=None, rows=5, placeholder=""):
        base = {"class": "form-control", "rows": rows, "data-rich": "1"}
        if placeholder:
            base["placeholder"] = placeholder
        base.update(attrs or {})
        super().__init__(base)


class RichTextField(forms.CharField):
    widget = RichTextarea

    def __init__(self, *args, rows=5, placeholder="", **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("strip", False)
        super().__init__(*args, **kwargs)
        self.widget = RichTextarea(rows=rows, placeholder=placeholder)

    def clean(self, value):
        # Assainir avant la validation : un contenu réduit à néant par le
        # filtre doit être vu comme vide par le champ obligatoire.
        return super().clean(clean(value))
