"""Table de cache.

DatabaseCache n'est pas un modèle : sa table se crée par une commande. La
lancer depuis une migration évite d'ajouter une étape au déploiement, et rend
la table présente partout où les migrations passent, tests compris.
"""

from django.core.management import call_command
from django.db import migrations

TABLE = "psc_cache"


def create(apps, schema_editor):
    call_command("createcachetable", TABLE, database=schema_editor.connection.alias,
                 verbosity=0)


def drop(apps, schema_editor):
    schema_editor.execute(f"DROP TABLE IF EXISTS {schema_editor.quote_name(TABLE)}")


class Migration(migrations.Migration):
    dependencies = [("core", "0004_alter_news_body")]

    operations = [migrations.RunPython(create, drop)]
