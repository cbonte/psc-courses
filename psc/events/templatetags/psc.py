from django import template
from django.utils.safestring import mark_safe

from events.models import month_label

register = template.Library()


@register.simple_tag
def date_range(edition):
    """« 12 avril 2027 » ou « 12 au 14 avril 2027 »."""
    start, end = edition.date_start, edition.date_end
    if start == end:
        return f"{start.day} {month_label(start.month)} {start.year}"
    if (start.month, start.year) == (end.month, end.year):
        return f"{start.day} au {end.day} {month_label(start.month)} {start.year}"
    if start.year == end.year:
        return (
            f"{start.day} {month_label(start.month)} au "
            f"{end.day} {month_label(end.month)} {start.year}"
        )
    return (
        f"{start.day} {month_label(start.month)} {start.year} au "
        f"{end.day} {month_label(end.month)} {end.year}"
    )


@register.simple_tag
def countdown(edition):
    """« aujourd'hui », « demain », « dans 12 jours »."""
    days = edition.days_until
    if days < 0:
        return ""
    if days == 0:
        return "aujourd'hui"
    if days == 1:
        return "demain"
    if days == 7:
        return "dans 1 semaine"
    if days < 31:
        return f"dans {days} jours"
    return ""


@register.inclusion_tag("partials/_rating.html")
def rating(score, count=None):
    """Cinq étoiles remplies au prorata de la note sur 5."""
    value = float(score or 0)
    return {
        "percent": max(0.0, min(100.0, value * 20.0)),
        "value": value,
        "count": count,
        "has_score": score is not None,
    }


@register.filter
def contrast_on(hex_color):
    """Noir ou blanc, selon la luminance de la couleur de fond."""
    color = (hex_color or "#6c757d").lstrip("#")
    if len(color) != 6:
        return "#ffffff"
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#212529" if luminance > 0.6 else "#ffffff"


@register.simple_tag
def query_toggle(request, key, value):
    """Ajoute ou retire une valeur d'un filtre multiple, en conservant le reste."""
    params = request.GET.copy()
    values = params.getlist(key)
    if value in values:
        values.remove(value)
    else:
        values.append(value)
    params.setlist(key, values)
    params.pop("page", None)
    encoded = params.urlencode()
    return mark_safe(f"?{encoded}" if encoded else "?")


@register.simple_tag
def query_replace(request, **kwargs):
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, "", False):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return mark_safe(f"?{encoded}" if encoded else "?")


@register.filter
def lookup(mapping, key):
    """Accès à un dictionnaire par clé variable, impossible nativement."""
    if not mapping:
        return None
    return mapping.get(key)
