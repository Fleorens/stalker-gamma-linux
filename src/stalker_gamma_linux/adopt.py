"""Commande `import` : adopter une installation GAMMA déjà présente sur le disque.

Le cas qui motive ce module n'est pas théorique : GOG distribue G.A.M.M.A. en
« mod en un clic » depuis fin 2025, et sous Linux (via Heroic) l'installation
se bloque après le téléchargement — 130 Gio sur le disque, aucun moyen de
jouer (Heroic#5063). Même situation pour une install manuelle interrompue, ou
pour un dossier partagé avec un dual-boot Windows. Redemander à ces gens de
retélécharger 146 Gio est une réponse absurde : les fichiers sont là.

**Ce que fait `import` :** il *repère* Anomaly et l'instance MO2 sous un
dossier donné, puis marque les étapes de téléchargement comme faites dans
l'état persisté. Le reste du pipeline (`install`) enchaîne alors sur ce qui
manque vraiment — retrait de ReShade, préfixe Proton, configuration de
l'instance, raccourci — sans re-télécharger.

**Ce qu'il ne fait pas :** copier ou déplacer quoi que ce soit. Quand les
dossiers trouvés ne sont pas déjà au layout attendu (`<racine>/anomaly` et
`<racine>/gamma`), on pose des **liens symboliques** vers eux. Zéro octet
dupliqué, opération réversible d'un `rm`, et tout l'aval (gamma-launcher,
winepath, MO2) continue de ne voir que le layout standard.

**Détection par marqueurs, pas par chemins connus.** On ne code en dur aucun
emplacement GOG/Heroic/Steam : on cherche `AnomalyLauncher.exe` et
`ModOrganizer.exe`. Ça marche pour toutes les origines, y compris celles qui
n'existent pas encore, et ça ne ment pas quand la structure est inattendue.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _

ProgressCallback = Callable[[str], None]

ANOMALY_MARKER = "AnomalyLauncher.exe"
MO2_MARKER = "ModOrganizer.exe"

# Profondeur de recherche sous le dossier fourni. 3 couvre les cas réels
# (`<dossier>`, `<dossier>/GAMMA/gamma`, `<dossier>/Games/GAMMA/anomaly`) sans
# transformer un `import ~/` distrait en parcours intégral du home.
MAX_DEPTH = 3

# Étapes que l'adoption dispense de rejouer : les deux téléchargements. Le
# retrait de ReShade, le préfixe, l'instance MO2 et le raccourci restent à
# faire — ce sont des actions locales, rapides, et rien ne dit qu'elles ont
# été effectuées sur l'installation adoptée (une install GOG, par exemple,
# arrive avec ReShade en place).
ADOPTED_STEPS: tuple[str, ...] = ("anomaly", "gamma")


class AdoptionError(Exception):
    """L'adoption ne peut pas aboutir (rien trouvé, ou cible déjà occupée)."""


@dataclass(frozen=True, slots=True)
class FoundInstall:
    """Ce qui a été repéré sur le disque, avant toute décision."""

    anomaly: Path
    gamma: Path

    @property
    def native_root(self) -> Path | None:
        """Racine commune si les deux dossiers sont déjà au layout attendu, sinon `None`.

        C'est le cas fréquent d'une install faite en suivant les guides
        (`<racine>/anomaly` + `<racine>/gamma`) : il n'y a alors rien à lier,
        on adopte la racine telle quelle.
        """
        if (
            self.anomaly.name == "anomaly"
            and self.gamma.name == "gamma"
            and self.anomaly.parent == self.gamma.parent
        ):
            return self.anomaly.parent
        return None


@dataclass(frozen=True, slots=True)
class AdoptionPlan:
    """Décision d'adoption : la racine retenue et les liens à poser."""

    found: FoundInstall
    root: Path
    links: tuple[tuple[Path, Path], ...]  # (lien à créer, cible)

    @property
    def is_in_place(self) -> bool:
        return not self.links


def _find_marker(source: Path, marker: str, *, max_depth: int = MAX_DEPTH) -> Path | None:
    """Dossier le moins profond contenant `marker`, ou `None`.

    Parcours en largeur pour que `<src>/anomaly` l'emporte sur un
    `<src>/gamma/anomaly` imbriqué : le premier est la vraie installation,
    le second peut être une copie partielle du layout GAMMA.
    """
    level = [source]
    for _depth in range(max_depth + 1):
        next_level: list[Path] = []
        for directory in level:
            try:
                if (directory / marker).is_file():
                    return directory
                next_level.extend(child for child in directory.iterdir() if child.is_dir())
            except OSError:
                continue  # dossier illisible : on l'ignore plutôt que d'échouer
        if not next_level:
            return None
        level = next_level
    return None


def discover(source: Path) -> FoundInstall:
    """Repère Anomaly et l'instance MO2 sous `source`. Lève `AdoptionError` si incomplet."""
    if not source.is_dir():
        raise AdoptionError(_("{source} is not a directory.").format(source=source))

    anomaly = _find_marker(source, ANOMALY_MARKER)
    gamma = _find_marker(source, MO2_MARKER)
    missing = [
        marker
        for marker, found in ((ANOMALY_MARKER, anomaly), (MO2_MARKER, gamma))
        if found is None
    ]
    if missing:
        raise AdoptionError(
            _(
                "No GAMMA install found under {source}: {markers} not found "
                "within {depth} levels.\nPoint --source at the folder that "
                "contains the game (the one holding Anomaly and the Mod "
                "Organizer 2 instance)."
            ).format(source=source, markers=" and ".join(missing), depth=MAX_DEPTH)
        )
    assert anomaly is not None and gamma is not None  # noqa: S101 - garanti par `missing`
    return FoundInstall(anomaly=anomaly, gamma=gamma)


def _link_conflict(link: Path, destination: Path) -> str | None:
    """Message d'erreur si `link` est déjà occupé par autre chose que le bon lien."""
    if not link.exists() and not link.is_symlink():
        return None
    if link.is_symlink() and link.resolve() == destination.resolve():
        return None  # déjà adopté : rejouer `import` ne doit pas échouer
    return _(
        "{link} already exists and does not point at {destination}. "
        "Remove it (or pick another --target) and run the import again."
    ).format(link=link, destination=destination)


def plan(found: FoundInstall, target: Path | None = None) -> AdoptionPlan:
    """Décide de la racine à adopter et des liens à poser. Ne touche à rien."""
    native = found.native_root
    if native is not None and (target is None or target.resolve() == native.resolve()):
        return AdoptionPlan(found=found, root=native, links=())

    root = target if target is not None else DEFAULT_INSTALL_TARGET
    links = ((root / "anomaly", found.anomaly), (root / "gamma", found.gamma))
    conflicts = [message for link, dest in links if (message := _link_conflict(link, dest))]
    if conflicts:
        raise AdoptionError("\n".join(conflicts))
    return AdoptionPlan(found=found, root=root, links=links)


def apply(plan: AdoptionPlan, *, on_progress: ProgressCallback | None = None) -> None:
    """Pose les liens manquants et marque les étapes téléchargées comme faites."""
    progress = on_progress or print
    for link, destination in plan.links:
        if link.is_symlink():
            continue  # déjà posé par un import précédent (cf. `_link_conflict`)
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(destination, target_is_directory=True)
        progress(_("Linked {link} → {destination}").format(link=link, destination=destination))
    for step in ADOPTED_STEPS:
        state_module.mark_done(plan.root, step)


def format_plan(plan: AdoptionPlan) -> str:
    lines = [
        _("Found:"),
        _("  Anomaly           {path}").format(path=plan.found.anomaly),
        _("  Mod Organizer 2   {path}").format(path=plan.found.gamma),
        "",
        _("Adopting as install root: {root}").format(root=plan.root),
    ]
    if plan.is_in_place:
        lines.append(_("  (already in the expected layout — nothing to link)"))
    else:
        lines.append(_("  Links to create (no file is copied or moved):"))
        lines.extend(
            _("    {link} → {destination}").format(link=link, destination=destination)
            for link, destination in plan.links
        )
    return "\n".join(lines)


def run_import(
    source: Path,
    target: Path | None = None,
    *,
    dry_run: bool = False,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Commande CLI `import`. Retourne 0 au succès, 1 si rien n'a pu être adopté."""
    progress = on_progress or print
    try:
        adoption = plan(discover(source), target)
    except AdoptionError as error:
        progress(_("Error: {error}").format(error=error))
        return 1

    progress(format_plan(adoption))
    if dry_run:
        progress(_("\nDry run: nothing was written."))
        return 0

    apply(adoption, on_progress=progress)
    progress(
        _(
            "\nImported. The downloads are considered done — nothing will be "
            "re-downloaded.\nFinish the setup (ReShade removal, Proton prefix, "
            "MO2 instance, shortcut) with:\n"
            "    stalker-gamma-linux install --target {root}\n\n"
            "If the modpack itself is incomplete (an interrupted download), run "
            "`stalker-gamma-linux update --target {root}` instead — it re-runs the "
            "modpack install, and backs up your MO2 profiles first."
        ).format(root=adoption.root)
    )
    return 0
