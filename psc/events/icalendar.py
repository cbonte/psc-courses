"""Génération de flux iCalendar, sans dépendance externe.

Le besoin se limite à des évènements sur journée entière : une quarantaine de
lignes suffisent, contre une bibliothèque à suivre dans le temps.
"""

import datetime

from django.utils import timezone

PRODID = "-//Paris Sport Club//Calendrier des courses//FR"
ONE_DAY = datetime.timedelta(days=1)


def escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line):
    """Repli des lignes à 75 octets, comme l'exige la RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not chunks else 74
        if len(current) + len(encoded) > limit:
            chunks.append(current)
            current = b""
        current += encoded
    chunks.append(current)
    return "\r\n ".join(chunk.decode("utf-8") for chunk in chunks)


def _date(value):
    return value.strftime("%Y%m%d")


def build_calendar(editions, name="Calendrier PSC", site_url=""):
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        "X-WR-TIMEZONE:Europe/Paris",
    ]
    for edition in editions:
        summary = edition.event.name
        if edition.status == edition.Status.PROVISIONAL:
            summary = f"[à confirmer] {summary}"
        description = edition.description or edition.event.description
        lines += [
            "BEGIN:VEVENT",
            f"UID:edition-{edition.pk}@paris-sport-club",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{_date(edition.date_start)}",
            # DTEND est exclusif pour un évènement sur journées entières.
            f"DTEND;VALUE=DATE:{_date(edition.date_end + ONE_DAY)}",
            fold(f"SUMMARY:{escape(summary)}"),
        ]
        if edition.event.location:
            lines.append(fold(f"LOCATION:{escape(edition.event.location)}"))
        if description:
            lines.append(fold(f"DESCRIPTION:{escape(description)}"))
        url = edition.registration_url or edition.event.website
        if not url and site_url:
            url = f"{site_url}{edition.get_absolute_url()}"
        if url:
            lines.append(fold(f"URL:{escape(url)}"))
        if edition.status == edition.Status.CANCELED:
            lines.append("STATUS:CANCELLED")
        elif edition.status == edition.Status.PROVISIONAL:
            lines.append("STATUS:TENTATIVE")
        else:
            lines.append("STATUS:CONFIRMED")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
