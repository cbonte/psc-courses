"""Données de référence : disciplines et critères d'évaluation.

Idempotent : relançable sans créer de doublons.
"""

from django.core.management.base import BaseCommand

from events.models import Discipline, FeedbackCriterion

# Les identifiants et les couleurs reprennent les pastilles historiques du club.
DISCIPLINES = [
    ("tri", "Triathlon", "#cc6666", 10),
    ("duathlon", "Duathlon", "#ff9966", 20),
    ("run", "Course à pied", "#e0a800", 30),
    ("trail", "Trail", "#99cc33", 40),
    ("swim", "Natation", "#3399cc", 50),
    ("swimrun", "Swimrun", "#6699cc", 60),
    ("cyclo", "Cyclisme", "#339966", 70),
    ("bikerun", "Bike and run", "#cc9966", 80),
    ("other", "Autre", "#8c8c8c", 90),
]

CRITERIA = [
    ("Organisation", 10),
    ("Parcours", 20),
    ("Ravitaillement", 30),
    ("Ambiance", 40),
]


class Command(BaseCommand):
    help = "Crée ou met à jour les disciplines et les critères d'évaluation."

    def handle(self, *args, **options):
        created = updated = 0
        for slug, label, color, position in DISCIPLINES:
            _, was_created = Discipline.objects.update_or_create(
                slug=slug, defaults={"label": label, "color": color, "position": position}
            )
            created += was_created
            updated += not was_created

        for label, position in CRITERIA:
            _, was_created = FeedbackCriterion.objects.update_or_create(
                label=label, defaults={"position": position}
            )
            created += was_created
            updated += not was_created

        self.stdout.write(
            self.style.SUCCESS(f"Références à jour : {created} créées, {updated} inchangées.")
        )
