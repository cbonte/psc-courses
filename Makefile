# Raccourcis de développement. « make aide » liste les cibles.

VENV ?= .venv
PORT ?= 5555
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
MANAGE := $(PY) psc/manage.py

.DEFAULT_GOAL := aide
.PHONY: aide install env migrate seed run test lint verifier deploiement collect reset

aide:
	@echo "Cibles disponibles :"
	@echo "  make install      installe le venv et les dépendances"
	@echo "  make env          crée un .env de développement complet"
	@echo "  make migrate      applique les migrations"
	@echo "  make seed         disciplines, critères et historique des épreuves"
	@echo "  make run          lance le serveur de développement (port $(PORT))"
	@echo "  make test         exécute la suite de tests"
	@echo "  make lint         analyse statique (ruff)"
	@echo "  make verifier     lint + tests + check Django (à lancer avant de pousser)"
	@echo "  make deploiement  contrôles de sécurité en configuration de production"
	@echo "  make reset        repart d'une base vide et réamorcée"

install:
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements-dev.txt
	@echo "Prêt. Enchaînez avec : make env migrate seed"

env:
	@test ! -f .env || (echo "Un .env existe déjà, rien n'est écrasé." && exit 1)
	@grep -vE '^(PSC_SECRET_KEY|PSC_ACCESS_PASSWORD_HASH)=$$' .env.example > .env
	@PSC_DEBUG=1 $(MANAGE) generate_secret_key >> .env
	@PSC_DEBUG=1 $(MANAGE) hash_access_password --password psc2027 \
		| grep '^PSC_ACCESS_PASSWORD_HASH=' >> .env
	@echo "Fichier .env créé. Mot de passe d'accès en développement : psc2027"

migrate:
	@mkdir -p data
	$(MANAGE) migrate

seed:
	$(MANAGE) seed_reference
	$(MANAGE) seed_history --purge-future

run:
	$(MANAGE) runserver $(PORT)

test:
	$(MANAGE) test core events

lint:
	$(VENV)/bin/ruff check .

verifier: lint
	$(MANAGE) check
	$(MANAGE) test core events

deploiement:
	PSC_DEBUG=0 PSC_ALLOWED_HOSTS=example.org $(MANAGE) check --deploy

collect:
	PSC_DEBUG=0 $(MANAGE) collectstatic --noinput

reset:
	rm -f data/psc.sqlite3 data/psc.sqlite3-wal data/psc.sqlite3-shm
	$(MAKE) migrate seed
