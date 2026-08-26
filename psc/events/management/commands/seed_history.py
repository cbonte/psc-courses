"""Historique des épreuves, sur lequel s'appuie la prédiction.

Ce n'est pas un calendrier prévisionnel : on ne saisit ici que des éditions
passées, à leur date réelle. L'année à venir n'est pas écrite en base, elle est
déduite par events.predictions à partir de cet historique, et n'existe qu'à
l'écran tant que personne ne l'a confirmée.

Chaque édition porte sa source. Trois niveaux :

  IDF26     calendrier régional Île-de-France 2026 (opentri.fr), dates publiées
  OFFICIEL  date publiée par l'organisateur ou une fiche encyclopédique
  FIXE      épreuve à date fixe dans l'année

Ce qui n'a pas pu être sourcé n'est pas inventé : il manque, et se saisit
depuis le site.

Aucune donnée personnelle n'est amorcée : ni membre, ni inscription, ni
évaluation. Ces informations n'appartiennent qu'aux personnes concernées et
n'ont pas à être fabriquées. Un test le vérifie.
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from events.models import Discipline, Event, EventEdition, EventFormat

IDF26 = "IDF26"
OFFICIEL = "OFFICIEL"
FIXE = "FIXE"

SOURCES = {
    IDF26: "Calendrier régional Île-de-France 2026 (opentri.fr).",
    OFFICIEL: "Date publiée par l'organisateur ou une fiche encyclopédique.",
    FIXE: "Épreuve à date fixe dans l'année.",
}

# (date, jours, nom, discipline, ville, département, source, formats)
EDITIONS = [
    # --- Grandes épreuves, dates vérifiées ------------------------------
    ("2024-04-07", 1, "Marathon de Paris", "run", "Paris", "75", OFFICIEL, [("42,195 km", "")]),
    ("2025-04-13", 1, "Marathon de Paris", "run", "Paris", "75", OFFICIEL, [("42,195 km", "")]),
    ("2026-04-12", 1, "Marathon de Paris", "run", "Paris", "75", OFFICIEL, [("42,195 km", "")]),
    ("2025-09-28", 1, "Paris-Versailles", "run", "Paris", "75", OFFICIEL, [("16,3 km", "")]),
    ("2026-09-27", 1, "Paris-Versailles", "run", "Paris", "75", OFFICIEL, [("16,3 km", "")]),
    ("2026-03-08", 1, "Semi-marathon de Paris", "run", "Paris", "75", OFFICIEL, [("21,1 km", "")]),
    ("2024-08-15", 1, "Embrunman", "tri", "Embrun", "05", FIXE,
     [("Longue distance", "3,8 km / 188 km / 42,2 km")]),
    ("2025-08-15", 1, "Embrunman", "tri", "Embrun", "05", FIXE,
     [("Longue distance", "3,8 km / 188 km / 42,2 km")]),
    ("2026-08-15", 1, "Embrunman", "tri", "Embrun", "05", FIXE,
     [("Longue distance", "3,8 km / 188 km / 42,2 km")]),
    ("2026-06-20", 2, "Openlakes Triathlon Champagne", "tri",
     "Sainte-Marie-du-Lac-Nuisement", "51", OFFICIEL,
     [("Full", "3,8 km / 180 km / 42 km"), ("Half", "1,9 km / 90 km / 21 km"),
      ("Olympique", "1,5 km / 40 km / 10 km")]),
    ("2026-08-22", 1, "Nage Ton Canal", "swim", "Pantin", "93", OFFICIEL,
     [("Eau libre", "1 km et 2 km"), ("Aquathlon", "")]),

    # --- Saison 2026 d'Île-de-France, calendrier régional ----------------
    ("2026-03-15", 1, "Duathlon de Paris Bois de Boulogne", "duathlon", "Paris", "75", IDF26, []),
    ("2026-03-21", 1, "Triathlon Indoor ACBB", "tri", "Boulogne-Billancourt", "92", IDF26, []),
    ("2026-03-22", 1, "Triathlon Super Sprint Paris 16e", "tri", "Paris", "75", IDF26,
     [("Super Sprint", "")]),
    ("2026-03-29", 1, "Triathlon Super Sprint Paris 19e", "tri", "Paris", "75", IDF26,
     [("Super Sprint", "")]),
    ("2026-03-29", 1, "Duathlon de Soisy", "duathlon", "Soisy-sous-Montmorency", "95", IDF26, []),
    ("2026-03-29", 1, "Duathlon de Meaux", "duathlon", "Meaux", "77", IDF26, []),
    ("2026-04-12", 1, "Triathlon Avenir de Courbevoie", "tri", "Courbevoie", "92", IDF26, []),
    ("2026-04-12", 1, "Triathlon de Fresnes", "tri", "Fresnes", "94", IDF26, []),
    ("2026-04-19", 1, "Triathlon Super Sprint Paris 20e", "tri", "Paris", "75", IDF26,
     [("Super Sprint", "200 m / 5 km / 1,5 km")]),
    ("2026-04-19", 1, "Triathlon de Chevilly-Larue", "tri", "Chevilly-Larue", "94", IDF26, []),
    ("2026-04-19", 1, "Cross Triathlon du Stade Français", "tri", "Saint-Cloud", "92", IDF26, []),
    ("2026-04-19", 1, "Run and Bike de Noiseau", "bikerun", "Noiseau", "94", IDF26, []),
    ("2026-05-02", 1, "Harmonie Mutuelle Swimrun de Paris", "swimrun", "Jablines", "77", IDF26, []),
    ("2026-05-03", 1, "Fuse Triathlon", "tri", "Ville-d'Avray", "92", IDF26, []),
    ("2026-05-08", 1, "Triathlon du Nautil", "tri", "Pontault-Combault", "77", IDF26, []),
    ("2026-05-10", 1, "Triathlon des Mureaux", "tri", "Verneuil-sur-Seine", "78", IDF26, []),
    ("2026-05-10", 1, "Cross Duathlon de Villejuif", "duathlon", "Villejuif", "94", IDF26, []),
    ("2026-05-23", 1, "Fontainebleau Swimrun Indoor", "swimrun", "Fontainebleau", "77", IDF26, []),
    ("2026-05-30", 2, "Versailles Triathlon Festival", "tri", "Versailles", "78", IDF26,
     [("S", ""), ("M", "")]),
    ("2026-05-31", 1, "Triathlon d'Andrésy", "tri", "Andrésy", "78", IDF26, []),
    ("2026-06-07", 1, "Cross Triathlon de Maisons-Laffitte", "tri", "Maisons-Laffitte", "78",
     IDF26, [("Cross", "VTT")]),
    ("2026-06-14", 1, "Aquathlon de Corbeil-Essonnes", "swim", "Corbeil-Essonnes", "91", IDF26, []),
    ("2026-06-28", 1, "Triathlon Pays de Brie", "tri", "La Ferté-sous-Jouarre", "77", IDF26, []),
    ("2026-07-05", 1, "Canathlon de l'Ourcq", "swimrun", "Aulnay-sous-Bois", "93", IDF26, []),
    ("2026-07-12", 1, "IRONMAN 70.3 Versailles", "tri", "Versailles", "78", IDF26,
     [("70.3", "1,9 km / 90 km / 21,1 km")]),
    ("2026-08-30", 1, "Aquathlon Paris 19", "swim", "Paris", "75", IDF26, []),
    ("2026-09-06", 1, "Aquathlon du Chesnay-Rocquencourt", "swim", "Le Chesnay-Rocquencourt",
     "78", IDF26, []),
    ("2026-09-12", 1, "TriaLong et TriaCourt Île-de-France", "tri", "Bois-le-Roi", "77", IDF26,
     [("TriaLong", ""), ("TriaCourt", "1,5 km / 40 km / 10 km")]),
    ("2026-09-19", 1, "Triathlon des Roses", "tri", "Saint-Cloud", "92", IDF26, []),
    ("2026-09-27", 1, "Cross Triathlon de Jablines-Annet", "tri", "Jablines", "77", IDF26, []),
    ("2026-10-04", 1, "XTriathlon Cergy-Pontoise", "tri", "Neuville-sur-Oise", "95", IDF26, []),
    ("2026-10-11", 1, "Triathlon de Sartrouville", "duathlon", "Sartrouville", "78", IDF26, []),
    ("2026-10-11", 1, "Cross Duathlon de Draveil", "duathlon", "Draveil", "91", IDF26, []),
    ("2026-11-08", 1, "Triathlon Super Sprint du RMA", "tri", "Paris", "75", IDF26, []),
    ("2026-11-08", 1, "Bike and Run d'Ozoir", "bikerun", "Ozoir-la-Ferrière", "77", IDF26, []),
    ("2026-11-22", 1, "Bike and Run de Palaiseau Polytechnique", "bikerun", "Palaiseau", "91",
     IDF26, []),
]


class Command(BaseCommand):
    help = "Charge l'historique des épreuves. L'année à venir en est déduite, pas écrite."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche sans enregistrer.")
        parser.add_argument(
            "--purge-future",
            action="store_true",
            help="Retire d'abord les éditions postérieures à la dernière année de l'historique.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        disciplines = {d.slug: d for d in Discipline.objects.all()}
        missing = {row[3] for row in EDITIONS} - set(disciplines)
        if missing:
            self.stderr.write(
                f"Disciplines absentes : {', '.join(sorted(missing))}. "
                f"Lancez d'abord « manage.py seed_reference »."
            )
            return

        last_year = max(int(row[0][:4]) for row in EDITIONS)

        if options["purge_future"] and not options["dry_run"]:
            removed = EventEdition.all_objects.filter(date_start__year__gt=last_year).delete()[0]
            if removed:
                self.stdout.write(f"{removed} enregistrement(s) postérieurs à {last_year} retirés.")

        created = skipped = 0
        for raw_date, days, name, slug, city, dept, source, formats in EDITIONS:
            start = datetime.date.fromisoformat(raw_date)
            end = start + datetime.timedelta(days=days - 1)

            if options["dry_run"]:
                self.stdout.write(f"{start:%d/%m/%Y}  {source:<9} {name}")
                continue

            event, _ = Event.all_objects.get_or_create(
                name=name,
                defaults={"discipline": disciplines[slug], "city": city, "department": dept},
            )
            edition, was_created = EventEdition.all_objects.get_or_create(
                event=event,
                date_start=start,
                defaults={
                    "date_end": end,
                    "status": EventEdition.Status.CONFIRMED,
                    "description": f"Source de la date : {SOURCES[source]}",
                },
            )
            if not was_created:
                skipped += 1
                continue
            created += 1
            for position, (format_name, distance) in enumerate(formats, start=1):
                EventFormat.objects.get_or_create(
                    edition=edition,
                    name=format_name,
                    defaults={"distance": distance, "position": position * 10},
                )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Essai à blanc : rien n'a été enregistré."))
            return

        self.stdout.write(
            self.style.SUCCESS(f"{created} éditions passées créées, {skipped} déjà présentes.")
        )
        self.stdout.write(
            f"Le calendrier {last_year + 1} n'est pas peuplé : il apparaîtra comme "
            f"propositions à confirmer, déduites de cet historique."
        )
