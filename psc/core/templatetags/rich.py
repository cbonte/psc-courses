from django import template
from django.utils.safestring import mark_safe

from core import richtext

register = template.Library()


@register.filter(name="rich")
def rich(value):
    """Affiche du texte riche déjà assaini.

    Le nettoyage est refait ici : il est idempotent, et cela garantit qu'un
    contenu entré par un autre chemin (import, console) ne passe pas en clair.
    """
    return mark_safe(richtext.clean(value))


@register.filter(name="rich_text")
def rich_text(value, limit=None):
    """Version texte, pour un résumé ou un attribut."""
    return richtext.to_text(value, int(limit) if limit else None)
