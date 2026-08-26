from django.urls import path

from core import club_views, views

app_name = "core"

urlpatterns = [
    path("acces/", views.access, name="access"),
    path("moi/", views.identity_picker, name="identity_picker"),
    path("moi/recherche/", views.identity_search, name="identity_search"),
    path("moi/choisir/", views.identity_set, name="identity_set"),
    path("moi/creer/", views.identity_create, name="identity_create"),
    path("moi/restaurer/", views.identity_restore, name="identity_restore"),
    path("moi/oublier/", views.identity_clear, name="identity_clear"),
    path("healthz", views.healthz, name="healthz"),
    # Gestion du club : ce que faisait l'administration, dans l'application.
    path("club/", club_views.hub, name="club"),
    path("club/disciplines/", club_views.disciplines, name="disciplines"),
    path("club/disciplines/<int:pk>/", club_views.discipline_row, name="discipline_row"),
    path("club/disciplines/<int:pk>/modifier/", club_views.discipline_edit,
         name="discipline_edit"),
    path("club/disciplines/<int:pk>/supprimer/", club_views.discipline_delete,
         name="discipline_delete"),
    path("club/criteres/", club_views.criteria, name="criteria"),
    path("club/criteres/<int:pk>/", club_views.criterion_row, name="criterion_row"),
    path("club/criteres/<int:pk>/modifier/", club_views.criterion_edit, name="criterion_edit"),
    path("club/criteres/<int:pk>/supprimer/", club_views.criterion_delete,
         name="criterion_delete"),
    path("club/annonces/", club_views.news, name="news"),
    path("club/annonces/<int:pk>/", club_views.news_row, name="news_row"),
    path("club/annonces/<int:pk>/modifier/", club_views.news_edit, name="news_edit"),
    path("club/annonces/<int:pk>/supprimer/", club_views.news_delete, name="news_delete"),
    path("club/membres/", club_views.members, name="members"),
    path("club/membres/<int:pk>/", club_views.member_row, name="member_row"),
    path("club/membres/<int:pk>/modifier/", club_views.member_edit, name="member_edit"),
    path("club/journal/", club_views.activity, name="activity"),
]
