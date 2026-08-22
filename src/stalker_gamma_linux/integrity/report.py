"""Comparaison référence ↔ disque, et attribution des écarts à leur mod.

Quatre catégories, et elles n'ont pas du tout le même sens pour l'utilisateur :

- `changed` — le fichier existe des deux côtés, son MD5 a bougé. C'est le
  symptôme qu'on cherche : corruption, écrasement par un autre outil,
  troncature après un disque plein.
- `removed` — présent dans la référence, absent du disque. Même famille.
- `added` — présent sur le disque, absent de la référence. Ce sont, dans
  l'immense majorité des cas, **les fichiers de l'utilisateur** : un mod ajouté
  à la main, un `.ltx` retouché, une config MO2. Jamais une avarie.
- `unreadable` — le fichier est là mais illisible. Ni « changé » ni
  « supprimé » : on ne sait pas, et le dire est plus utile que de trancher.

L'attribution au mod se lit dans le chemin relatif : sous `gamma/mods/`, le
premier segment **est** le dossier du mod (`312- Gunslinger … /gamedata/…`).
Pas d'heuristique à inventer — c'est la structure que MO2 impose.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import sizing
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity.scan import UnreadableFile

# Un fichier posé directement sous `mods/` n'appartient à aucun mod (MO2 n'en
# met pas ; c'est donc forcément quelque chose que l'utilisateur y a laissé).
ROOT_MOD = ""

# Au-delà, on résume au lieu d'imprimer des milliers de lignes : un utilisateur
# qui a perdu un disque n'a pas besoin de la liste complète pour comprendre.
_MAX_LISTED_PER_CATEGORY = 10


@dataclass(frozen=True, slots=True)
class ModFinding:
    """Écarts relevés dans un dossier de mod donné."""

    name: str
    changed: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def is_damaged(self) -> bool:
        """Le mod est abîmé — par opposition à « l'utilisateur y a ajouté des choses ».

        `added` seul n'est **jamais** une avarie : c'est ce qui distingue un mod
        à réparer d'un mod auquel on ne doit surtout pas toucher.
        """
        return bool(self.changed or self.removed)

    @property
    def has_user_files(self) -> bool:
        return bool(self.added)


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """Résultat d'un passage de vérification, prêt à être rendu ou à piloter une réparation."""

    mods_dir: Path
    changed: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unreadable: tuple[UnreadableFile, ...] = ()
    scanned_files: int = 0
    scanned_bytes: int = 0
    # Lignes de la référence qu'on n'a pas su relire : elles produisent de faux
    # « supprimé », il faut pouvoir le dire au lieu de le laisser croire.
    unparsed_baseline_lines: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not (self.changed or self.added or self.removed or self.unreadable)

    @property
    def is_intact(self) -> bool:
        """Rien d'abîmé — des ajouts de l'utilisateur ne comptent pas comme une avarie."""
        return not (self.changed or self.removed or self.unreadable)


def mod_of(relative: str) -> str:
    """Dossier de mod auquel appartient un chemin relatif à `mods/` (`ROOT_MOD` si aucun)."""
    head, separator, _tail = relative.partition("/")
    return head if separator else ROOT_MOD


def compare(
    baseline: Mapping[str, str], observed: Mapping[str, str]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """`(changed, added, removed)` entre la référence et ce qui est sur le disque."""
    changed = tuple(
        sorted(
            path
            for path, digest in observed.items()
            if path in baseline and baseline[path] != digest
        )
    )
    added = tuple(sorted(set(observed) - set(baseline)))
    removed = tuple(sorted(set(baseline) - set(observed)))
    return changed, added, removed


def group_by_mod(report: IntegrityReport) -> tuple[ModFinding, ...]:
    """Écarts regroupés par dossier de mod, triés par nom."""
    names = sorted(
        {mod_of(path) for path in (*report.changed, *report.added, *report.removed)},
    )
    return tuple(
        ModFinding(
            name=name,
            changed=_paths_of(name, report.changed),
            added=_paths_of(name, report.added),
            removed=_paths_of(name, report.removed),
        )
        for name in names
    )


def damaged_mods(report: IntegrityReport) -> tuple[ModFinding, ...]:
    """Uniquement les mods réellement abîmés (fichiers modifiés ou disparus)."""
    return tuple(finding for finding in group_by_mod(report) if finding.is_damaged)


def _paths_of(mod: str, paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(path for path in paths if mod_of(path) == mod)


def format_report(report: IntegrityReport) -> str:
    """Rendu texte du rapport, dans le vocabulaire de `doctor`."""
    lines = [
        _("Scanned: {files} files, {size} GiB in {path}").format(
            files=report.scanned_files,
            size=f"{report.scanned_bytes / sizing.GIB:.1f}",
            path=report.mods_dir,
        ),
        "",
    ]
    if report.unparsed_baseline_lines:
        lines.append(
            _(
                "[WARNING] {count} unreadable line(s) in the reference were ignored — "
                "the files they described are reported as removed."
            ).format(count=len(report.unparsed_baseline_lines))
        )
        lines.append("")

    if report.is_clean:
        lines.append(_("[ OK ] Unchanged — the install matches its reference exactly."))
        return "\n".join(lines)

    lines.extend(_category_lines(_("[CHANGED]"), _("Modified"), report.changed))
    lines.extend(_category_lines(_("[MISSING]"), _("Missing"), report.removed))
    lines.extend(_category_lines(_("[ INFO ]"), _("Added (yours — left alone)"), report.added))
    lines.extend(
        _category_lines(
            _("[UNREADABLE]"),
            _("Unreadable"),
            tuple(f"{entry.relative} — {entry.reason}" for entry in report.unreadable),
        )
    )

    findings = damaged_mods(report)
    if findings:
        lines.append(_("Mods affected:"))
        lines.extend(
            _("  - {name}: {changed} modified, {removed} missing").format(
                name=finding.name or _("(loose files under mods/)"),
                changed=len(finding.changed),
                removed=len(finding.removed),
            )
            for finding in findings
        )
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _category_lines(label: str, title: str, paths: tuple[str, ...]) -> list[str]:
    if not paths:
        return []
    # Ponctuation dans la chaîne traduite, pas concaténée : le français met une
    # espace avant les deux-points, l'anglais non.
    lines = [_("{label} {title}: {count}").format(label=label, title=title, count=len(paths))]
    lines.extend(f"    {path}" for path in paths[:_MAX_LISTED_PER_CATEGORY])
    if len(paths) > _MAX_LISTED_PER_CATEGORY:
        lines.append(
            _("    … and {count} more").format(count=len(paths) - _MAX_LISTED_PER_CATEGORY)
        )
    lines.append("")
    return lines
