"""Histogramme des inscriptions, calculé pour un rendu HTML côté serveur.

Une bibliothèque de graphiques pesait 68 Ko compressés pour un seul
histogramme empilé. Les proportions tiennent ici en quelques lignes, et la
page ne charge plus rien.
"""

from dataclasses import dataclass, field


@dataclass
class Slice:
    """Une part d'une colonne empilée."""

    label: str
    color: str
    value: int
    percent: float


@dataclass
class Column:
    """Un mois de l'histogramme."""

    label: str
    caption: str
    total: int
    percent: float
    slices: list = field(default_factory=list)


@dataclass
class Chart:
    """Histogramme empilé, rendu en HTML.

    Une première version en SVG a été abandonnée pour deux raisons. Les
    coordonnées passaient par le formatage localisé de Django, qui écrit les
    décimales avec une virgule, invalide en SVG. Et le texte d'un SVG mis à
    l'échelle rétrécit avec lui : sur un téléphone, les libellés devenaient
    illisibles. En HTML, les libellés sont du texte ordinaire.
    """

    year: int
    total: int = 0
    top: int = 0
    columns: list = field(default_factory=list)
    legend: list = field(default_factory=list)
    rows: list = field(default_factory=list)

    @property
    def is_empty(self):
        return self.total == 0


def nice_ceiling(value):
    """Plafond lisible : 1, 2, 5, 10, 20... juste au-dessus de la valeur."""
    if value <= 4:
        return max(value, 1)
    step = 1
    while step * 10 < value:
        step *= 10
    for factor in (1, 2, 5, 10):
        if step * factor >= value:
            return step * factor
    return value


def build(year, datasets, month_names):
    chart = Chart(year=year)
    chart.total = sum(sum(d["data"]) for d in datasets)
    chart.legend = [{"label": d["label"], "color": d["color"]} for d in datasets]
    chart.rows = [
        {"label": d["label"], "color": d["color"], "data": d["data"], "total": sum(d["data"])}
        for d in datasets
    ]

    stacks = [sum(d["data"][month] for d in datasets) for month in range(12)]
    chart.top = nice_ceiling(max(stacks, default=0)) if chart.total else 0

    for month in range(12):
        total = stacks[month]
        column = Column(
            label=month_names[month],
            caption=f"{month_names[month]} {year} : "
            + (f"{total} inscription{'s' if total > 1 else ''}" if total else "aucune inscription"),
            total=total,
            percent=(100 * total / chart.top) if chart.top else 0,
        )
        for dataset in datasets:
            value = dataset["data"][month]
            if value:
                column.slices.append(
                    Slice(
                        label=dataset["label"],
                        color=dataset["color"],
                        value=value,
                        percent=100 * value / total,
                    )
                )
        chart.columns.append(column)
    return chart


@dataclass
class Bar:
    """Une barre d'un graphique rendu en HTML plutôt qu'en SVG.

    Les deux graphiques ci-dessous sont des séries d'une seule valeur : des
    éléments de bloc avec une hauteur en pourcentage suffisent, restent
    cliquables et se lisent au clavier sans effort.
    """

    label: str
    caption: str
    value: int
    percent: float
    href: str = ""
    current: bool = False


def month_density(months, year, url_for_month):
    """Densité d'épreuves par mois, servant aussi de navigation.

    `months` est la liste des mois affichés, telle que la vue les groupe.
    Les mois vides restent présents : c'est l'information la plus utile du
    bandeau, celle des creux de la saison.
    """
    from events.models import month_abbr, month_label

    counts = {entry["number"]: len(entry["editions"]) for entry in months}
    top = max(counts.values(), default=0)
    bars = []
    for number in range(1, 13):
        count = counts.get(number, 0)
        name = month_label(number)
        bars.append(
            Bar(
                label=month_abbr(number),
                caption=f"{name.capitalize()} {year} : "
                + (f"{count} épreuve{'s' if count > 1 else ''}" if count else "aucune épreuve"),
                value=count,
                percent=(100 * count / top) if top else 0,
                href=url_for_month(number) if count else "",
            )
        )
    return bars


def participation_history(editions, today):
    """Nombre de membres inscrits, édition par édition.

    Répond à une question que la liste des éditions ne montre pas : est-ce
    que le club y va, et est-ce que cela monte ?
    """
    entries = sorted(editions, key=lambda item: item.date_start)
    top = max((item.participation_count for item in entries), default=0)
    bars = []
    for edition in entries:
        count = edition.participation_count
        bars.append(
            Bar(
                label=str(edition.year),
                caption=f"{edition.year} : "
                + (f"{count} membre{'s' if count > 1 else ''}" if count else "personne"),
                value=count,
                percent=(100 * count / top) if top else 0,
                href=f"#edition-{edition.pk}",
                current=edition.date_end >= today,
            )
        )
    return bars
