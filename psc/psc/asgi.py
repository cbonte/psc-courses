"""Point d'entrée ASGI, tenu à jour par symétrie avec wsgi.py.

Il n'est pas utilisé : ASGI_APPLICATION n'est pas déclaré, et toutes les vues
sont synchrones.
"""

import os
import sys

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE_PROJET not in sys.path:
    sys.path.insert(0, RACINE_PROJET)

from django.core.asgi import get_asgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "psc.settings")

application = get_asgi_application()
