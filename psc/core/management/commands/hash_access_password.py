import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Génère la valeur à placer dans PSC_ACCESS_PASSWORD_HASH."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Mot de passe en clair. Omis, il est demandé sans écho.",
        )

    def handle(self, *args, **options):
        password = options["password"] or getpass.getpass("Mot de passe du club : ")
        if not password:
            self.stderr.write("Mot de passe vide, rien à faire.")
            return
        self.stdout.write("")
        self.stdout.write("À copier dans le fichier .env :")
        self.stdout.write("")
        self.stdout.write(f"PSC_ACCESS_PASSWORD_HASH={make_password(password)}")
        self.stdout.write("")
