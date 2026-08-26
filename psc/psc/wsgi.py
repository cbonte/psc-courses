"""Point d'entrée WSGI.

En local, manage.py vit dans psc/ : Python y cherche les modules, et
« psc.settings » désigne psc/psc/settings.py. Sur un hébergement qui importe
ce fichier depuis la racine du dépôt, « psc » désigne le répertoire externe et
le réglage devient introuvable. Le répertoire qui contient manage.py est donc
ajouté explicitement au chemin de recherche.
"""

import os
import sys

RACINE_PROJET = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE_PROJET not in sys.path:
    sys.path.insert(0, RACINE_PROJET)

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "psc.settings")

application = get_wsgi_application()
