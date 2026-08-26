from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect
from django.urls import reverse

ACCESS_SESSION_KEY = "psc_access_granted"
MEMBER_SESSION_KEY = "psc_member_id"


def _is_exempt(request):
    """Chemins accessibles sans le mot de passe du club."""
    path = request.path
    if path.startswith(settings.STATIC_URL):
        return True
    return path in {reverse("core:access"), reverse("core:healthz")}


class SharedAccessMiddleware:
    """Porte d'entrée du site : un mot de passe unique pour tout le club.

    Ce n'est délibérément pas de l'authentification : le mot de passe ouvre le
    site, il n'identifie personne. L'identité est déclarative et vit dans
    CurrentMemberMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.PSC_ACCESS_PASSWORD_HASH:
            if not settings.DEBUG:
                raise ImproperlyConfigured(
                    "PSC_ACCESS_PASSWORD_HASH n'est pas défini : le site serait ouvert à tous. "
                    "Générer la valeur avec « python psc/manage.py hash_access_password »."
                )
            # En développement, on laisse passer mais on le signale dans les pages.
            request.access_unprotected = True
            return self.get_response(request)

        request.access_unprotected = False
        if request.session.get(ACCESS_SESSION_KEY) or _is_exempt(request):
            return self.get_response(request)

        target = reverse("core:access")
        if request.method == "GET" and request.path != "/":
            target = f"{target}?suite={request.get_full_path()}"
        return redirect(target)


class CurrentMemberMiddleware:
    """Expose sur la requête le membre déclaré en session, ou None."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Résolution immédiate plutôt que paresseuse : un objet paresseux
        # enveloppant None n'est pas None, et casse silencieusement les filtres
        # de requête qui le reçoivent.
        request.member = _resolve_member(request)
        return self.get_response(request)


def _resolve_member(request):
    from core.models import Member

    member_id = request.session.get(MEMBER_SESSION_KEY)
    if not member_id:
        return None
    member = Member.objects.filter(pk=member_id, is_active=True).first()
    if member is None:
        # Membre supprimé ou désactivé : on nettoie la session.
        request.session.pop(MEMBER_SESSION_KEY, None)
    return member
