"""Helpers de formatage purs pour la GUI — indépendants de GTK, testables seuls."""

from __future__ import annotations

_GIB = 1024**3


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
