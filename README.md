# psc-courses

Le calendrier des courses du Paris Sport Club : triathlon, duathlon, course à
pied, natation. Chaque membre y trouve les épreuves à venir, déclare celles
qu'il court, et évalue celles qu'il a courues.

Application Django, rendu serveur, sans compte utilisateur.

## Comment ça marche

Le calendrier s'entretient par ses membres. Chacun ajoute une course, corrige
une date, supprime une erreur.

L'année à venir n'est pas saisie, elle est déduite. Une course des trois
dernières saisons apparaît d'elle-même sur l'année suivante, en pointillé, à sa
date reportée au même jour de la semaine. « Confirmer le 7 mars » l'inscrit au
calendrier ; « Une autre date » ouvre le formulaire si elle a bougé ; « Pas
cette année » l'écarte, réversiblement.

Rien n'est effacé pour de bon. La corbeille conserve tout et remet en place d'un
clic, et un journal retient qui a fait quoi.

## Trois partis pris

**Aucun rôle.** Il n'y a ni administrateur ni membre privilégié, et pas
d'administration Django : disciplines, critères d'évaluation, annonces, membres,
corbeille et journal se règlent dans l'application, sous l'onglet « Le club ».
Toute personne entrée peut tout modifier ; ce qui protège n'est pas une
permission mais la réversibilité et la traçabilité.

**Un seul mot de passe pour tout le club.** Il n'y a pas de compte à créer :
un mot de passe partagé ouvre le site, puis chaque visiteur indique qui il est
et son navigateur s'en souvient. Ce n'est délibérément pas de
l'authentification : qui connaît le mot de passe peut se déclarer comme
n'importe quel membre. C'est acceptable pour un calendrier de club à deux
conditions, aucune donnée sensible sur le site, et aucune suppression
définitive accessible aux visiteurs.

**Django réduit à ce qui sert.** Un seul moteur de gabarits, SQLite, ni API ni
couche REST, ni `contrib.admin` ni `contrib.auth`, Bootstrap 5 et HTMX côté
navigateur. Une seule dépendance : Django.

## Démarrer

```bash
make install     # venv et dépendances
make env         # .env de développement (mot de passe d'accès : psc2027)
make migrate
make seed        # disciplines, critères, calendrier prévisionnel 2027
make run
```

Le site répond sur http://127.0.0.1:5555/. Le port se change à la volée :
`make run PORT=8900`. Il n'y a pas de compte à créer : le mot de passe du club
suffit, et tout se règle depuis l'onglet « Le club ».

## Structure

```
psc/
  psc/          réglages, URLs racine
  core/         accès partagé, identité des membres, annonces, écrans du club
  events/       disciplines, courses, éditions, formats, inscriptions, évaluations
  templates/    gabarits Django
  static/       CSS et JS maison, bibliothèques dans vendor/
data/           base SQLite (hors dépôt)
```

## Commandes utiles

| Commande | Effet |
|---|---|
| `make test` | la suite complète |
| `make verifier` | analyse statique, contrôles Django et tests |
| `make deploiement` | contrôles de sécurité en configuration de production |
| `manage.py generate_secret_key` | valeur de `PSC_SECRET_KEY` |
| `manage.py hash_access_password` | valeur de `PSC_ACCESS_PASSWORD_HASH` |
| `manage.py seed_reference` | disciplines et critères d'évaluation |
| `manage.py seed_calendar_2027` | calendrier prévisionnel, `--dry-run` pour un essai |

Les tests se lancent avec les étiquettes d'application (`test core events`) :
`manage.py` vit dans `psc/`, la découverte automatique depuis la racine du
dépôt ne trouverait rien.

## Configuration

Tout passe par des variables d'environnement, lues depuis `.env` à la racine.
Voir [.env.example](.env.example). Aucun secret n'est versionné.

En production, `PSC_DEBUG` doit rester vide et `PSC_SECRET_KEY`,
`PSC_ALLOWED_HOSTS` et `PSC_ACCESS_PASSWORD_HASH` sont obligatoires : le site
refuse de démarrer sans mot de passe d'accès plutôt que de s'ouvrir à tous.

## Le calendrier 2027

`seed_calendar_2027` amorce une vingtaine d'épreuves, **toutes marquées « à
confirmer »**. Ce n'est pas un historique des participations du club : cette
information n'est pas publique. C'est une proposition bâtie sur les épreuves
récurrentes d'Île-de-France et les grands rendez-vous nationaux, dont chaque
édition indique d'où vient sa date. Le club doit la valider épreuve par
épreuve. Le détail de la méthode est en tête du fichier
`psc/events/management/commands/seed_calendar_2027.py`.

## Sauvegarde

La base est un fichier. `cp data/psc.sqlite3 sauvegarde-$(date +%F).sqlite3`
suffit, serveur arrêté ou via `sqlite3 data/psc.sqlite3 ".backup ..."` à chaud.
