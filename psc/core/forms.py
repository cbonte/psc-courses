from django import forms

from core.models import Member


class AccessForm(forms.Form):
    password = forms.CharField(
        label="Mot de passe du club",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "autocomplete": "current-password",
                "autofocus": "autofocus",
            }
        ),
    )


class MemberForm(forms.ModelForm):
    existing = None

    class Meta:
        model = Member
        fields = ["first_name", "last_name"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "given-name"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "family-name"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        first = (cleaned.get("first_name") or "").strip()
        last = (cleaned.get("last_name") or "").strip()
        cleaned["first_name"] = first
        cleaned["last_name"] = last
        # Un membre qui se déclare deux fois n'est pas une erreur de saisie :
        # on réutilisera la fiche existante plutôt que d'afficher un refus.
        self.existing = (
            Member.objects.filter(first_name__iexact=first, last_name__iexact=last).first()
            if first
            else None
        )
        return cleaned

    def validate_unique(self):
        if self.existing is not None:
            return
        super().validate_unique()

    def validate_constraints(self):
        # L'unicité insensible à la casse est portée par une contrainte
        # d'expression, vérifiée ici et non par validate_unique().
        if self.existing is not None:
            return
        super().validate_constraints()
