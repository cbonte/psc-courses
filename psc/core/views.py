from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from core.forms import AccessForm, MemberForm
from core.middleware import ACCESS_SESSION_KEY, MEMBER_SESSION_KEY
from core.models import Member


def _client_key(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "?")
    return f"psc-access-attempts:{ip}"


def _safe_next(request):
    candidate = request.POST.get("suite") or request.GET.get("suite") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return reverse("events:dashboard")


@require_http_methods(["GET", "POST"])
def access(request):
    """Demande le mot de passe unique partagé par le club."""
    if request.session.get(ACCESS_SESSION_KEY):
        return redirect(_safe_next(request))

    key = _client_key(request)
    attempts = cache.get(key, 0)
    locked = attempts >= settings.PSC_ACCESS_MAX_ATTEMPTS
    form = AccessForm(request.POST or None)

    if request.method == "POST" and not locked:
        if form.is_valid() and check_password(
            form.cleaned_data["password"], settings.PSC_ACCESS_PASSWORD_HASH
        ):
            cache.delete(key)
            request.session[ACCESS_SESSION_KEY] = True
            request.session.cycle_key()
            request.session[ACCESS_SESSION_KEY] = True
            return redirect(_safe_next(request))

        attempts += 1
        cache.set(key, attempts, settings.PSC_ACCESS_LOCKOUT_SECONDS)
        locked = attempts >= settings.PSC_ACCESS_MAX_ATTEMPTS
        if not locked:
            form.add_error("password", "Mot de passe incorrect.")

    return render(
        request,
        "core/access.html",
        {
            "form": form,
            "locked": locked,
            "lockout_minutes": settings.PSC_ACCESS_LOCKOUT_SECONDS // 60,
            "suite": request.GET.get("suite", ""),
        },
        status=429 if locked else 200,
    )


def identity_picker(request):
    """Fragment « Qui es-tu ? » : liste des membres et création."""
    query = request.GET.get("q", "")
    members = Member.objects.active().search(query)[:40]
    return render(
        request,
        "core/_identity_picker.html",
        {"members": members, "query": query, "form": MemberForm()},
    )


def identity_search(request):
    """Fragment de résultats, rechargé à la frappe par HTMX."""
    query = request.GET.get("q", "")
    members = Member.objects.active().search(query)[:40]
    return render(request, "core/_identity_results.html", {"members": members, "query": query})


@require_POST
def identity_set(request):
    """Enregistre le membre déclaré, en session et côté navigateur."""
    member = Member.objects.filter(pk=request.POST.get("member"), is_active=True).first()
    if member is None:
        return HttpResponse("Membre inconnu.", status=400)
    request.session[MEMBER_SESSION_KEY] = member.pk
    return _identity_response(request, member)


@require_POST
def identity_create(request):
    """Crée un membre absent de la liste, puis l'adopte comme identité."""
    form = MemberForm(request.POST)
    if form.is_valid():
        member = form.existing or form.save()
        if not member.is_active:
            # Un ancien membre qui se redéclare revient dans le club.
            member.is_active = True
            member.save(update_fields=["is_active", "updated_at"])
        request.session[MEMBER_SESSION_KEY] = member.pk
        return _identity_response(request, member)
    return render(
        request,
        "core/_identity_picker.html",
        {"members": Member.objects.active()[:40], "query": "", "form": form},
        status=422,
    )


@require_POST
def identity_restore(request):
    """Rejoue l'identité mémorisée par le navigateur après expiration de session.

    Appelée par le JavaScript de la page, jamais par un humain.
    """
    member = Member.objects.filter(pk=request.POST.get("member"), is_active=True).first()
    if member is None:
        return JsonResponse({"restored": False}, status=404)
    request.session[MEMBER_SESSION_KEY] = member.pk
    return JsonResponse({"restored": True, "name": member.full_name})


@require_POST
def identity_clear(request):
    """« Ce n'est pas moi » : oublie l'identité déclarée."""
    request.session.pop(MEMBER_SESSION_KEY, None)
    response = redirect(request.META.get("HTTP_REFERER") or reverse("events:dashboard"))
    response["HX-Refresh"] = "true"
    return response


def _identity_response(request, member):
    """Réponse HTMX : rafraîchit la page et laisse le navigateur mémoriser."""
    response = HttpResponse(status=204)
    response["HX-Trigger"] = f'{{"psc:member-set": {{"id": {member.pk}}}}}'
    response["HX-Refresh"] = "true"
    return response


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")
