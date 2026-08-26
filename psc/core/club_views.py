"""Écrans de gestion du club.

Il n'y a pas de rôle : ces pages sont accessibles à tout membre entré avec le
mot de passe du club, comme le reste du site. La sécurité tient à la
réversibilité et à la traçabilité, pas à des permissions.
"""

from django.db.models import Count, ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.club_forms import DisciplineForm, FeedbackCriterionForm, MemberEditForm, NewsForm
from core.models import Activity, Member, News
from events.models import Discipline, EventEdition, FeedbackCriterion


def _member(request):
    return getattr(request, "member", None)


def _needs_identity():
    response = HttpResponse(status=409)
    response["HX-Trigger"] = '{"psc:identity-needed": {}}'
    return response


def hub(request):
    """Point d'entrée unique vers tout ce qui se règle."""
    return render(
        request,
        "core/club/hub.html",
        {
            "nav": "club",
            "section": "hub",
            "counts": {
                "disciplines": Discipline.objects.count(),
                "criteria": FeedbackCriterion.objects.filter(is_active=True).count(),
                "news": News.objects.filter(is_published=True).count(),
                "members": Member.objects.active().count(),
                "trash": EventEdition.all_objects.deleted().count(),
                "activity": Activity.objects.count(),
            },
        },
    )


# --------------------------------------------------------------------------
# Un même moteur pour les trois listes simples : disciplines, critères, annonces
# --------------------------------------------------------------------------


def _simple_list(request, *, config):
    """Liste et création. Le formulaire de création est en tête de page."""
    member = _member(request)
    form = config["form"](request.POST or None)

    if request.method == "POST":
        if member is None:
            return _needs_identity()
        if form.is_valid():
            obj = form.save()
            Activity.log(member, Activity.Action.CREATED, obj)
            return redirect(config["url"])

    return render(
        request,
        config["template"],
        {
            "nav": "club",
            "section": config["section"],
            "form": form,
            "objects": config["queryset"](),
            "config": config,
        },
        status=422 if request.method == "POST" else 200,
    )


def _simple_edit(request, pk, *, config):
    obj = get_object_or_404(config["model"], pk=pk)
    member = _member(request)
    form = config["form"](request.POST or None, instance=obj)

    if request.method == "POST":
        if member is None:
            return _needs_identity()
        if form.is_valid():
            form.save()
            Activity.log(member, Activity.Action.UPDATED, obj)
            return render(request, config["row_template"], {"object": obj, "config": config})

    return render(
        request,
        config["row_form_template"],
        {"object": obj, "form": form, "config": config},
        status=422 if request.method == "POST" else 200,
    )


def _simple_row(request, pk, *, config):
    obj = get_object_or_404(config["model"], pk=pk)
    return render(request, config["row_template"], {"object": obj, "config": config})


DISCIPLINES = {
    "model": Discipline,
    "form": DisciplineForm,
    "url": "core:disciplines",
    "section": "disciplines",
    "template": "core/club/disciplines.html",
    "row_template": "core/club/_discipline_row.html",
    "row_form_template": "core/club/_discipline_form.html",
    "queryset": lambda: Discipline.objects.annotate(uses=Count("events")),
}

CRITERIA = {
    "model": FeedbackCriterion,
    "form": FeedbackCriterionForm,
    "url": "core:criteria",
    "section": "criteria",
    "template": "core/club/criteria.html",
    "row_template": "core/club/_criterion_row.html",
    "row_form_template": "core/club/_criterion_form.html",
    "queryset": lambda: FeedbackCriterion.objects.annotate(uses=Count("scores")),
}

NEWS = {
    "model": News,
    "form": NewsForm,
    "url": "core:news",
    "section": "news",
    "template": "core/club/news.html",
    "row_template": "core/club/_news_row.html",
    "row_form_template": "core/club/_news_form.html",
    "queryset": lambda: News.objects.all(),
}


def disciplines(request):
    return _simple_list(request, config=DISCIPLINES)


def discipline_edit(request, pk):
    return _simple_edit(request, pk, config=DISCIPLINES)


def discipline_row(request, pk):
    return _simple_row(request, pk, config=DISCIPLINES)


@require_POST
def discipline_delete(request, pk):
    return _protected_delete(request, pk, config=DISCIPLINES)


def criteria(request):
    return _simple_list(request, config=CRITERIA)


def criterion_edit(request, pk):
    return _simple_edit(request, pk, config=CRITERIA)


def criterion_row(request, pk):
    return _simple_row(request, pk, config=CRITERIA)


@require_POST
def criterion_delete(request, pk):
    return _protected_delete(request, pk, config=CRITERIA)


def news(request):
    form = NewsForm(request.POST or None, initial={"published_at": timezone.localtime()})
    return _simple_list(request, config={**NEWS, "form": lambda *a, **k: form})


def news_edit(request, pk):
    return _simple_edit(request, pk, config=NEWS)


def news_row(request, pk):
    return _simple_row(request, pk, config=NEWS)


@require_POST
def news_delete(request, pk):
    """Une annonce se retire mais ne se perd pas."""
    entry = get_object_or_404(News.objects.all(), pk=pk)
    member = _member(request)
    if member is None:
        return _needs_identity()
    entry.soft_delete(member)
    Activity.log(member, Activity.Action.DELETED, entry)
    return render(request, "core/club/_removed_row.html", {"label": entry.title})


def _protected_delete(request, pk, *, config):
    """Refuse de supprimer ce qui est encore utilisé, et dit pourquoi."""
    obj = get_object_or_404(config["model"], pk=pk)
    member = _member(request)
    if member is None:
        return _needs_identity()
    label = str(obj)
    try:
        obj.delete()
    except ProtectedError:
        return render(
            request,
            config["row_template"],
            {"object": obj, "config": config, "blocked": True},
            status=409,
        )
    Activity.log(member, Activity.Action.DELETED, obj)
    return render(request, "core/club/_removed_row.html", {"label": label})


# --------------------------------------------------------------------------
# Membres et journal
# --------------------------------------------------------------------------


def members(request):
    query = request.GET.get("q", "")
    people = (
        Member.objects.search(query)
        .annotate(races=Count("participations"))
        .order_by("-is_active", "first_name", "last_name")
    )
    return render(
        request,
        "core/club/members.html",
        {"nav": "club", "section": "members", "members": people, "query": query},
    )


def member_edit(request, pk):
    person = get_object_or_404(Member.objects.all(), pk=pk)
    member = _member(request)
    form = MemberEditForm(request.POST or None, instance=person)
    if request.method == "POST":
        if member is None:
            return _needs_identity()
        if form.is_valid():
            form.save()
            Activity.log(member, Activity.Action.UPDATED, person)
            return render(request, "core/club/_member_row.html", {"object": person})
    return render(
        request,
        "core/club/_member_form.html",
        {"object": person, "form": form},
        status=422 if request.method == "POST" else 200,
    )


def member_row(request, pk):
    return render(
        request,
        "core/club/_member_row.html",
        {"object": get_object_or_404(Member.objects.all(), pk=pk)},
    )


def activity(request):
    entries = Activity.objects.select_related("member")[:200]
    return render(
        request, "core/club/activity.html", {"nav": "club", "section": "activity", "entries": entries}
    )
