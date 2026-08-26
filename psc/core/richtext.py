"""Texte riche saisi par les membres.

Le texte est saisi en WYSIWYG et stocké en HTML. Ce HTML vient du navigateur,
donc de l'utilisateur : il est assaini **côté serveur** avant enregistrement,
jamais à l'affichage. C'est le seul endroit du projet où du HTML échappe à
l'échappement automatique des gabarits, et c'est pourquoi tout passe par ici.

Marquer du HTML utilisateur comme sûr à l'affichage, sans l'avoir filtré,
suffit à faire exécuter n'importe quel script chez le visiteur suivant.
"""

import re

import nh3

# Volontairement étroit : mise en forme, listes, liens. Ni images, ni tableaux,
# ni styles en ligne. Ce que la barre d'outils propose, et rien de plus.
ALLOWED_TAGS = {
    "p", "br",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li",
    "blockquote",
    "h3", "h4",
    "a",
}

ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}

ALLOWED_SCHEMES = {"http", "https", "mailto"}

_TAG = re.compile(r"<[a-zA-Z/!][^>]*>")
_BLANK = re.compile(r"(&nbsp;|\s)+")


def looks_like_html(value):
    return bool(_TAG.search(value or ""))


def clean(value):
    """Assainit du HTML saisi par un membre.

    Un contenu qui n'a jamais été du HTML (texte tapé avant l'éditeur, ou
    saisi sans JavaScript) est converti en paragraphes, pour que les sauts de
    ligne survivent à l'affichage.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if not looks_like_html(value):
        value = plain_to_html(value)
    cleaned = nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel="noopener noreferrer",
    )
    return "" if is_blank(cleaned) else cleaned


def plain_to_html(value):
    """Texte brut vers paragraphes, en conservant les lignes vides."""
    from django.utils.html import escape

    blocks = [block.strip() for block in re.split(r"\n\s*\n", value) if block.strip()]
    return "".join(
        "<p>" + "<br>".join(escape(line) for line in block.splitlines()) + "</p>"
        for block in blocks
    )


def is_blank(value):
    """L'éditeur rend « <p><br></p> » pour un contenu vide."""
    without_tags = _TAG.sub(" ", value or "")
    return not _BLANK.sub("", without_tags)


def to_text(value, limit=None):
    """Version texte, pour les résumés et les flux iCal."""
    text = _TAG.sub(" ", value or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text
