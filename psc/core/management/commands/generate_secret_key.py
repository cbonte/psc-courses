from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key


class Command(BaseCommand):
    help = "Génère la valeur à placer dans PSC_SECRET_KEY."

    def handle(self, *args, **options):
        self.stdout.write(f"PSC_SECRET_KEY={get_random_secret_key()}")
