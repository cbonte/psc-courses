from django.urls import path

from events import views

app_name = "events"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("calendrier/", views.calendar_redirect, name="calendar"),
    path("calendrier/<int:year>/", views.calendar_year, name="calendar_year"),
    path("calendrier.ics", views.calendar_ics, name="calendar_ics"),
    path("calendrier/<int:year>.ics", views.calendar_ics, name="calendar_year_ics"),
    # Saisie, ouverte à tout membre déclaré. Déclarée avant course/<slug>/,
    # qui capturerait autrement « ajouter » comme un identifiant de course.
    path("calendrier/ajouter/", views.edition_create, name="edition_create"),
    path("calendrier/<int:year>/ajouter/", views.edition_create, name="edition_create_year"),
    path("course/<slug:slug>/", views.event_detail, name="event_detail"),
    path("edition/<int:pk>/modifier/", views.edition_edit, name="edition_edit"),
    path("edition/<int:pk>/carte/", views.edition_card, name="edition_card"),
    path("edition/<int:pk>/supprimer/", views.edition_delete, name="edition_delete"),
    path("edition/<int:pk>/restaurer/", views.edition_restore, name="edition_restore"),
    path("corbeille/", views.trash, name="trash"),
    # Prédictions : l'édition de l'an prochain, proposée avant d'exister.
    path(
        "prediction/<int:pk>/<int:year>/confirmer/",
        views.prediction_confirm,
        name="prediction_confirm",
    ),
    path(
        "prediction/<int:pk>/<int:year>/ajuster/",
        views.prediction_adjust,
        name="prediction_adjust",
    ),
    path(
        "prediction/<int:pk>/<int:year>/ecarter/",
        views.prediction_dismiss,
        name="prediction_dismiss",
    ),
    path(
        "prediction/<int:pk>/<int:year>/remettre/",
        views.prediction_restore,
        name="prediction_restore",
    ),
    # Participation et évaluations.
    path("edition/<int:pk>/participation/", views.participation_toggle, name="participation"),
    path("edition/<int:pk>/inscrits/", views.participants_panel, name="participants"),
    path("edition/<int:pk>/evaluation/", views.feedback_form, name="feedback"),
    path("edition/<int:pk>/evaluations/", views.feedback_summary, name="feedback_summary"),
    path("edition/<int:pk>.ics", views.edition_ics, name="edition_ics"),
    path("mes-courses/", views.my_events, name="my_events"),
    path("statistiques.json", views.stats_json, name="stats_json"),
]
