from django.conf import settings


def site(request):
    """Valeurs disponibles dans tous les gabarits."""
    return {
        "current_member": getattr(request, "member", None),
        "access_unprotected": getattr(request, "access_unprotected", False),
        "debug": settings.DEBUG,
    }
