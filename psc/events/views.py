import datetime
import json
from collections import OrderedDict, defaultdict

from django.db.models import Avg, Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.models import Activity, News
from events import chart as chart_builder
from events.forms import EditionForm, FeedbackForm
from events.icalendar import build_calendar
from events.models import (
    Discipline,
    Event,
    EventEdition,
    EventFormat,
    Feedback,
    Participation,
    PredictionDismissal,
    month_label,
)
from events.predictions import predicted_editions

ENCOURAGEMENT_WINDOW_DAYS = 7


def _current_year():
    return timezone.localdate().year


def _member_or_none(request):
    return getattr(request, "member", None)


# --------------------------------------------------------------------------
# Tableau de bord
# --------------------------------------------------------------------------


def dashboard(request):
    today = timezone.localdate()
    horizon = today + datetime.timedelta(days=ENCOURAGEMENT_WINDOW_DAYS)

    upcoming = (
        EventEdition.objects.visible()
        .with_details()
        .upcoming(today)
        .order_by("date_start")[:8]
    )

    this_week = (
        Participation.objects.filter(
            edition__date_start__gte=today,
            edition__date_start__lte=horizon,
            status=Participation.Status.REGISTERED,
        )
        .exclude(edition__status=EventEdition.Status.CANCELED)
        .select_related("member", "edition", "edition__event", "edition__event__discipline")
        .order_by("edition__date_start", "member__first_name")
    )
    encouragements = OrderedDict()
    for participation in this_week:
        encouragements.setdefault(participation.edition, []).append(participation.member)

    recent_feedbacks = (
        Feedback.objects.select_related("member", "edition", "edition__event")
        .prefetch_related("scores", "scores__criterion")
        .order_by("-updated_at")[:5]
    )

    member = _member_or_none(request)
    my_next = []
    if member is not None:
        my_next = (
            Participation.objects.filter(member=member, edition__date_end__gte=today)
            .exclude(edition__status=EventEdition.Status.CANCELED)
            .select_related("edition", "edition__event", "edition__event__discipline", "format")
            .order_by("edition__date_start")[:5]
        )

    return render(
        request,
        "events/dashboard.html",
        {
            "upcoming": upcoming,
            "encouragements": encouragements,
            "recent_feedbacks": recent_feedbacks,
            "my_next": my_next,
            "news": News.objects.filter(is_published=True, published_at__lte=timezone.now())[:3],
            "chart": build_chart(_current_year()),
            "year": _current_year(),
            "has_any_edition": EventEdition.objects.exists(),
        },
    )


# --------------------------------------------------------------------------
# Calendrier
# --------------------------------------------------------------------------


def calendar_redirect(request):
    return redirect("events:calendar_year", year=_current_year())


def _filtered_editions(request, year):
    """Applique les filtres de l'URL. Partagé par la page et le fragment HTMX."""
    editions = (
        EventEdition.objects.with_details()
        .for_year(year)
        .prefetch_related("formats")
        .order_by("date_start", "event__name")
    )

    disciplines = request.GET.getlist("discipline")
    if disciplines:
        editions = editions.filter(event__discipline__slug__in=disciplines)

    statuses = request.GET.getlist("statut")
    if statuses:
        editions = editions.filter(status__in=statuses)
    else:
        editions = editions.exclude(status=EventEdition.Status.CANCELED)

    query = (request.GET.get("q") or "").strip()
    if query:
        editions = editions.filter(
            Q(event__name__icontains=query)
            | Q(event__city__icontains=query)
            | Q(description__icontains=query)
        )

    member = _member_or_none(request)
    if request.GET.get("mine") == "1" and member is not None:
        editions = editions.filter(participations__member=member)

    return editions, disciplines, statuses, query


def _group_by_month(editions):
    grouped = OrderedDict()
    for edition in editions:
        grouped.setdefault(edition.date_start.month, []).append(edition)
    return [
        {"number": month, "label": month_label(month), "editions": items}
        for month, items in grouped.items()
    ]


def _my_edition_ids(request, editions):
    member = _member_or_none(request)
    if member is None:
        return {}
    keys = [edition.pk for edition in editions if edition.pk]
    return dict(
        Participation.objects.filter(member=member, edition__in=keys).values_list(
            "edition_id", "status"
        )
    )


def _matches_filters(prediction, disciplines, query):
    """Applique à une prédiction les mêmes filtres qu'aux éditions réelles."""
    if disciplines and prediction.event.discipline.slug not in disciplines:
        return False
    if query:
        haystack = f"{prediction.event.name} {prediction.event.city}".lower()
        if query.lower() not in haystack:
            return False
    return True


def _calendar_context(request, year):
    editions, disciplines, statuses, query = _filtered_editions(request, year)
    editions = list(editions)

    # Les prédictions ne concernent que l'avenir, et disparaissent dès qu'on
    # ne regarde que ses propres épreuves.
    predictions = []
    if year >= _current_year() and request.GET.get("mine") != "1":
        if not statuses or EventEdition.Status.PROVISIONAL in statuses:
            predictions = [
                prediction
                for prediction in predicted_editions(year)
                if _matches_filters(prediction, disciplines, query)
            ]

    rows = sorted(editions + predictions, key=lambda item: (item.date_start, item.event.name))
    # dates() renvoie déjà une entrée par année ; y chaîner values_list()
    # annulerait ce regroupement et rendrait une entrée par édition.
    known_years = {day.year for day in EventEdition.objects.dates("date_start", "year")}
    navigable = known_years | {year, _current_year()}
    # Une année d'avance, pour commencer à poser la saison suivante.
    navigable.add(max(navigable) + 1)
    months = _group_by_month(rows)
    return {
        "year": year,
        "years": sorted(navigable),
        "months": months,
        "density": chart_builder.month_density(
            months, year, lambda number: f"#mois-{number:02d}"
        ),
        "edition_count": len(editions),
        "prediction_count": len(predictions),
        "disciplines": Discipline.objects.all(),
        "selected_disciplines": disciplines,
        "selected_statuses": statuses,
        "statuses": EventEdition.Status.choices,
        "query": query,
        "mine": request.GET.get("mine") == "1",
        "my_participations": _my_edition_ids(request, editions),
        "today": timezone.localdate(),
    }


def calendar_year(request, year):
    context = _calendar_context(request, year)
    template = (
        "events/_calendar_list.html"
        if request.headers.get("HX-Request") == "true"
        else "events/calendar.html"
    )
    return render(request, template, context)


# --------------------------------------------------------------------------
# Fiche course
# --------------------------------------------------------------------------


def event_detail(request, slug):
    event = get_object_or_404(Event.objects.select_related("discipline"), slug=slug)
    editions = (
        event.editions.with_details()
        .prefetch_related(
            "formats",
            Prefetch(
                "participations",
                queryset=Participation.objects.select_related("member", "format").order_by(
                    "member__first_name"
                ),
            ),
            Prefetch(
                "feedbacks",
                queryset=Feedback.objects.select_related("member").prefetch_related(
                    "scores", "scores__criterion"
                ),
            ),
        )
        .order_by("-date_start")
    )
    editions = list(editions)
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "history": chart_builder.participation_history(editions, timezone.localdate()),
            "back_url": reverse("events:calendar_year", args=[editions[0].year])
            if editions
            else reverse("events:calendar"),
            "back_label": f"Calendrier {editions[0].year}" if editions else "Calendrier",
            "editions": editions,
            "my_participations": _my_edition_ids(request, editions),
            "today": timezone.localdate(),
        },
    )


def my_events(request):
    member = _member_or_none(request)
    today = timezone.localdate()
    upcoming, past = [], []
    if member is not None:
        participations = (
            Participation.objects.filter(member=member)
            .select_related("edition", "edition__event", "edition__event__discipline", "format")
            .order_by("edition__date_start")
        )
        for participation in participations:
            (past if participation.edition.date_end < today else upcoming).append(participation)
        past.reverse()
    return render(
        request,
        "events/my_events.html",
        {"upcoming": upcoming, "past": past, "member": member},
    )


# --------------------------------------------------------------------------
# Participation
# --------------------------------------------------------------------------


@require_POST
def participation_toggle(request, pk):
    """Inscrit, met à jour ou retire le membre courant. Réponse HTMX."""
    edition = get_object_or_404(
        EventEdition.objects.select_related("event", "event__discipline"), pk=pk
    )
    member = _member_or_none(request)
    if member is None:
        response = HttpResponse(status=409)
        response["HX-Trigger"] = '{"psc:identity-needed": {}}'
        return response

    action = request.POST.get("action", "join")
    if action == "leave":
        Participation.objects.filter(member=member, edition=edition).delete()
    else:
        format_id = request.POST.get("format") or None
        status = request.POST.get("status") or Participation.Status.REGISTERED
        if status not in Participation.Status.values:
            status = Participation.Status.REGISTERED
        defaults = {"status": status}
        if format_id:
            defaults["format"] = edition.formats.filter(pk=format_id).first()
        Participation.objects.update_or_create(
            member=member, edition=edition, defaults=defaults
        )

    edition = (
        EventEdition.objects.with_details().prefetch_related("formats").get(pk=edition.pk)
    )
    response = render(
        request,
        "events/_participation.html",
        {
            "edition": edition,
            "my_participations": _my_edition_ids(request, [edition]),
            "today": timezone.localdate(),
        },
    )
    return _say(
        response,
        f"Vous n'êtes plus inscrit à {edition.event.name}."
        if action == "leave"
        else f"Inscription enregistrée pour {edition.event.name}.",
    )


# --------------------------------------------------------------------------
# Évaluations
# --------------------------------------------------------------------------


def feedback_form(request, pk):
    edition = get_object_or_404(
        EventEdition.objects.select_related("event", "event__discipline"), pk=pk
    )
    # Une course qui n'a pas eu lieu ne s'évalue pas.
    if not edition.can_be_reviewed:
        return render(
            request,
            "events/feedback_too_early.html",
            {"edition": edition},
            status=403,
        )

    member = _member_or_none(request)
    if member is None:
        return render(
            request, "events/feedback_form.html", {"edition": edition, "form": None}, status=200
        )

    instance = Feedback.objects.filter(member=member, edition=edition).first()
    form = FeedbackForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        feedback = form.save(commit=False)
        feedback.member = member
        feedback.edition = edition
        feedback.save()
        form.instance = feedback
        form.save_scores()
        return redirect(f"{edition.get_absolute_url()}")

    return render(request, "events/feedback_form.html", {"edition": edition, "form": form})


# --------------------------------------------------------------------------
# Export iCal
# --------------------------------------------------------------------------


def _ics_response(editions, name, request):
    site_url = f"{request.scheme}://{request.get_host()}"
    body = build_calendar(editions, name=name, site_url=site_url)
    response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="psc.ics"'
    return response


def calendar_ics(request, year=None):
    editions = EventEdition.objects.select_related("event").order_by("date_start")
    if year:
        editions = editions.for_year(year)
        name = f"Courses PSC {year}"
    else:
        editions = editions.filter(
            date_end__gte=timezone.localdate() - datetime.timedelta(days=365)
        )
        name = "Courses PSC"
    return _ics_response(editions, name, request)


def edition_ics(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    return _ics_response([edition], str(edition), request)


# --------------------------------------------------------------------------
# Statistiques
# --------------------------------------------------------------------------


def monthly_participation(year):
    """Inscriptions par mois et par discipline, pour une année.

    Sert au graphique du tableau de bord, rendu en SVG côté serveur, et à
    l'endpoint JSON pour qui voudrait rejouer les mêmes chiffres.
    """
    rows = (
        Participation.objects.filter(
            edition__date_start__year=year, status=Participation.Status.REGISTERED
        )
        .values(
            "edition__date_start__month",
            "edition__event__discipline__label",
            "edition__event__discipline__color",
        )
        .annotate(total=Count("id"))
    )
    series = defaultdict(lambda: [0] * 12)
    colors = {}
    for row in rows:
        label = row["edition__event__discipline__label"] or "Autre"
        colors[label] = row["edition__event__discipline__color"] or "#6c757d"
        series[label][row["edition__date_start__month"] - 1] = row["total"]
    return [
        {"label": label, "data": data, "color": colors[label]}
        for label, data in sorted(series.items())
    ]


def stats_json(request):
    """Les mêmes chiffres, en JSON."""
    year = int(request.GET.get("year") or _current_year())
    return JsonResponse(
        {
            "year": year,
            "labels": [month_label(month).capitalize() for month in range(1, 13)],
            "datasets": monthly_participation(year),
        }
    )


def feedback_summary(request, pk):
    """Fragment : toutes les évaluations d'une édition."""
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    feedbacks = (
        edition.feedbacks.select_related("member")
        .prefetch_related("scores", "scores__criterion")
        .annotate(avg=Avg("scores__score"))
        .order_by("-updated_at")
    )
    return render(
        request,
        "events/_feedback_list.html",
        {"edition": edition, "feedbacks": feedbacks, "detailed": True},
    )


# --------------------------------------------------------------------------
# Créer, corriger, supprimer une épreuve
#
# Ouvert à tout membre déclaré : le calendrier s'entretient par ceux qui le
# consultent. La contrepartie n'est pas une restriction mais la réversibilité :
# rien n'est effacé, tout est journalisé.
# --------------------------------------------------------------------------


def _card_response(request, edition, status=200):
    """Rend la carte d'une épreuve, telle qu'elle apparaît dans le calendrier."""
    edition = EventEdition.objects.with_details().prefetch_related("formats").get(pk=edition.pk)
    return render(
        request,
        "events/_edition_card.html",
        {
            "edition": edition,
            "my_participations": _my_edition_ids(request, [edition]),
            "today": timezone.localdate(),
        },
        status=status,
    )


def _return_to(request):
    """Où revenir après l'action, quand elle n'a pas été lancée du calendrier."""
    candidate = request.POST.get("return_to") or request.GET.get("return_to") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return ""


def _redirect_response(target):
    response = HttpResponse(status=204)
    response["HX-Redirect"] = target
    return response


def _say(response, message):
    """Fait annoncer un message à l'écran et aux lecteurs d'écran.

    Une action HTMX réussie ne laissait aucune trace audible : la carte
    changeait, et c'est tout.
    """
    response["HX-Trigger"] = json.dumps({"psc:said": {"message": message}})
    return response


def _needs_identity(request):
    """Réponse HTMX qui ouvre la question « Qui es-tu ? » au lieu d'échouer."""
    response = HttpResponse(status=409)
    response["HX-Trigger"] = '{"psc:identity-needed": {}}'
    return response


def edition_card(request, pk):
    """Retour à la carte après annulation d'une modification."""
    edition = get_object_or_404(EventEdition.objects.all(), pk=pk)
    return _card_response(request, edition)


def edition_create(request, year=None):
    member = _member_or_none(request)
    if member is None and request.method == "POST":
        return _needs_identity(request)

    year = year or _current_year()
    form = EditionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        edition = form.save(member=member)
        Activity.log(member, Activity.Action.CREATED, edition)
        response = HttpResponse(status=204)
        response["HX-Redirect"] = edition.get_absolute_url()
        return response

    if not request.POST:
        form = EditionForm(initial={"date_start": datetime.date(year, 1, 1)})
    return render(
        request,
        "events/_edition_form.html",
        {
            "form": form,
            "return_to": _return_to(request),
            "action": reverse("events:edition_create"),
            "title": "Ajouter une course",
            "submit_label": "Ajouter au calendrier",
            "suggestions": Event.objects.order_by("name").values_list("name", flat=True),
        },
        status=422 if request.method == "POST" else 200,
    )


def edition_edit(request, pk):
    edition = get_object_or_404(
        EventEdition.objects.select_related("event").prefetch_related("formats"), pk=pk
    )
    member = _member_or_none(request)
    if member is None and request.method == "POST":
        return _needs_identity(request)

    back = _return_to(request)
    form = EditionForm(request.POST or None, edition=edition)
    if request.method == "POST" and form.is_valid():
        form.save(member=member)
        Activity.log(member, Activity.Action.UPDATED, edition)
        # Depuis la fiche d'une course, la carte du calendrier n'aurait pas de
        # sens : on rend la page d'où le geste est parti.
        message = f"{edition.event.name} a été modifiée."
        return _say(
            _redirect_response(back) if back else _card_response(request, edition), message
        )

    return render(
        request,
        "events/_edition_form.html",
        {
            "form": form,
            "edition": edition,
            "return_to": back,
            "action": reverse("events:edition_edit", args=[edition.pk]),
            "cancel_url": back or reverse("events:edition_card", args=[edition.pk]),
            "title": f"Modifier l'édition {edition.year}",
            "submit_label": "Enregistrer",
            "suggestions": Event.objects.order_by("name").values_list("name", flat=True),
        },
        status=422 if request.method == "POST" else 200,
    )


@require_POST
def edition_delete(request, pk):
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    member = _member_or_none(request)
    if member is None:
        return _needs_identity(request)
    label = str(edition)
    edition.soft_delete(member)
    Activity.log(member, Activity.Action.DELETED, edition)
    back = _return_to(request)
    if back:
        return _say(_redirect_response(back), f"{label} a été supprimée.")
    return _say(
        render(request, "events/_edition_deleted.html", {"edition": edition, "label": label}),
        f"{label} a été supprimée. La corbeille la conserve.",
    )


@require_POST
def edition_restore(request, pk):
    edition = get_object_or_404(EventEdition.all_objects.select_related("event"), pk=pk)
    member = _member_or_none(request)
    edition.restore()
    if edition.event.is_deleted:
        edition.event.restore()
    Activity.log(member, Activity.Action.RESTORED, edition)
    if request.headers.get("HX-Request") == "true":
        return _say(_card_response(request, edition), f"{edition} est de retour au calendrier.")
    return redirect(edition.get_absolute_url())


def trash(request):
    """La corbeille : ce qui a été supprimé, et le bouton pour le reprendre."""
    editions = (
        EventEdition.all_objects.deleted()
        .select_related("event", "event__discipline", "deleted_by")
        .order_by("-deleted_at")
    )
    return render(
        request, "events/trash.html", {"editions": editions, "nav": "club", "section": "trash"}
    )


@require_POST
def prediction_confirm(request, pk, year):
    """Confirme en un clic l'édition prédite pour une course.

    C'est le chemin de création le plus fréquent : la date proposée est la
    bonne dans la plupart des cas, et il n'y a alors rien d'autre à saisir.
    """
    member = _member_or_none(request)
    if member is None:
        return _needs_identity(request)

    source = get_object_or_404(
        EventEdition.objects.select_related("event").prefetch_related("formats"), pk=pk
    )
    for prediction in predicted_editions(year):
        if prediction.source.pk != source.pk:
            continue
        # Confirmer engage la date : le membre affirme qu'elle est la bonne.
        # Elle reste corrigeable, et rétrogradable en « à confirmer » depuis le
        # formulaire.
        edition = EventEdition.objects.create(
            event=source.event,
            date_start=prediction.date_start,
            date_end=prediction.date_end,
            status=EventEdition.Status.CONFIRMED,
            description=source.description,
            registration_url=source.registration_url,
        )
        for entry in source.formats.all():
            EventFormat.objects.create(
                edition=edition,
                name=entry.name,
                distance=entry.distance,
                description=entry.description,
                position=entry.position,
            )
        Activity.log(member, Activity.Action.CREATED, edition, "confirmée depuis la prédiction")
        return _say(
            _card_response(request, edition),
            f"{edition.event.name} est inscrite au calendrier.",
        )

    # La course a été inscrite entretemps par quelqu'un d'autre.
    existing = EventEdition.objects.filter(event=source.event, date_start__year=year).first()
    if existing is not None:
        return _card_response(request, existing)
    return HttpResponse("Cette prédiction n'a plus lieu d'être.", status=410)


def prediction_adjust(request, pk, year):
    """Formulaire prérempli quand la date prédite doit être corrigée."""
    source = get_object_or_404(
        EventEdition.objects.select_related("event").prefetch_related("formats"), pk=pk
    )
    member = _member_or_none(request)
    if member is None and request.method == "POST":
        return _needs_identity(request)

    if request.method == "POST":
        form = EditionForm(request.POST)
        if form.is_valid():
            edition = form.save(member=member)
            Activity.log(form.cleaned_data and member, Activity.Action.CREATED, edition)
            return _card_response(request, edition)
    else:
        predicted = next(
            (p for p in predicted_editions(year) if p.source.pk == source.pk), None
        )
        start = predicted.date_start if predicted else source.date_start
        form = EditionForm(initial=EditionForm.initial_from(source, date_start=start))
        form.initial["status"] = EventEdition.Status.CONFIRMED

    return render(
        request,
        "events/_edition_form.html",
        {
            "form": form,
            "action": reverse("events:prediction_adjust", args=[source.pk, year]),
            "cancel_url": reverse("events:calendar_year", args=[year]),
            "title": f"Une autre date pour {year}",
            "submit_label": "Confirmer cette date",
            "suggestions": Event.objects.order_by("name").values_list("name", flat=True),
            "is_prediction": True,
        },
        status=422 if request.method == "POST" else 200,
    )


def participants_panel(request, pk):
    """Liste des inscrits, dépliée à la demande depuis la carte."""
    edition = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    participations = (
        edition.participations.select_related("member", "format")
        .order_by("status", "member__first_name")
    )
    return render(
        request,
        "events/_participants.html",
        {"edition": edition, "participations": participations},
    )


@require_POST
def prediction_dismiss(request, pk, year):
    """« Cette course n'a pas lieu cette année. »

    Sans ce geste, une course arrêtée resterait proposée indéfiniment, et le
    seul moyen de la faire taire serait de l'inscrire à tort.
    """
    member = _member_or_none(request)
    if member is None:
        return _needs_identity(request)
    source = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    PredictionDismissal.objects.get_or_create(
        event=source.event, year=year, defaults={"member": member}
    )
    Activity.log(
        member, Activity.Action.UPDATED, source.event, f"proposition {year} écartée"
    )
    return _say(
        render(
            request,
            "events/_prediction_dismissed.html",
            {"event": source.event, "source": source, "year": year},
        ),
        f"{source.event.name} n'est plus proposée pour {year}.",
    )


@require_POST
def prediction_restore(request, pk, year):
    """Remet une proposition écartée, si on s'est trompé."""
    source = get_object_or_404(EventEdition.objects.select_related("event"), pk=pk)
    PredictionDismissal.objects.filter(event=source.event, year=year).delete()
    prediction = next(
        (item for item in predicted_editions(year) if item.source.pk == source.pk), None
    )
    if prediction is None:
        return HttpResponse(status=204)
    return render(
        request,
        "events/_edition_card.html",
        {"edition": prediction, "my_participations": {}, "today": timezone.localdate()},
    )


def build_chart(year):
    """Prépare la géométrie de l'histogramme du tableau de bord."""
    from events.models import MONTH_ABBR

    return chart_builder.build(year, monthly_participation(year), MONTH_ABBR)
