"""Helpers de formatage purs pour la GUI — indépendants de GTK, testables seuls."""

from __future__ import annotations

import re

_GIB = 1024**3

# URL citée dans un message d'erreur (ex. la page ModDB d'un mod que le
# téléchargement n'a pas pu servir, cf. `engine.errors`). La ponctuation
# terminale d'une phrase française n'appartient pas à l'URL : `[^\s<>"']+`
# capture large, puis on rogne `.,;:)]` — sinon « ouvre https://…/addon. »
# produit un lien mort d'un caractère.
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_URL_TRAILING = ".,;:!?)]}»"


def first_url(text: str) -> str | None:
    """Première URL http(s) du texte, ponctuation de fin rognée. `None` s'il n'y en a pas."""
    match = _URL_RE.search(text)
    if match is None:
        return None
    return match.group(0).rstrip(_URL_TRAILING) or None


def parse_step_index(index: str) -> tuple[int, int] | None:
    """Décompose un index d'étape `Reporter` (« 3/7 ») en `(3, 7)`.

    Retourne `None` pour tout ce qui n'est pas exactement `n/total` avec
    `1 <= n <= total` : la vue progression retombe alors sur un rendu
    indéterminé plutôt que d'afficher une fraction fausse.
    """
    number, sep, total = index.partition("/")
    if sep != "/" or not number.isdigit() or not total.isdigit():
        return None
    parsed_number, parsed_total = int(number), int(total)
    if not 1 <= parsed_number <= parsed_total:
        return None
    return parsed_number, parsed_total


def format_gib(n_bytes: int) -> str:
    """« 245 GiB », « 1.5 GiB » — une décimale sous 10 GiB.

    L'unité affichée est bien le Gio (2³⁰ octets), ce que divise `_GIB` et ce que
    renvoie `shutil.disk_usage` : l'ancien libellé « GB » laissait croire à des
    gigaoctets décimaux et ne se comparait pas aux seuils de `sizing`.
    """
    gib = n_bytes / _GIB
    if gib >= 10:
        return f"{gib:.0f} GiB"
    return f"{gib:.1f} GiB"


def format_duration(seconds: float) -> str:
    """« 42 s », « 4 min 05 », « 1 h 02 min » — pour le temps écoulé d'une tâche."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d}"
    return f"{secs} s"
