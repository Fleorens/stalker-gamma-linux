"""Désinstallation propre : défaire ce qu'`install.sh` et l'app ont posé.

Un outil qu'on distribue doit savoir se retirer. Jusqu'ici, `install.sh` posait
un venv, deux liens dans `~/.local/bin`, une entrée bureau, une icône et
`umu-run`, puis l'application ajoutait un état, des préférences et des journaux
— et **rien** ne savait défaire tout ça.

Deux périmètres, volontairement séparés :

- **l'intégration** (entrées bureau, icônes, état, préférences, journaux) :
  quelques kilo-octets, recréés au prochain lancement, retirés par défaut ;
- **les données de jeu** (`<target>/{anomaly,gamma,cache,prefix}`) : ~146 Gio
  et des heures de téléchargement, plus les sauvegardes du joueur. Jamais
  touchées sans `--game-data` explicite.

`umu-run` n'est jamais retiré : il vit dans `~/.local/bin`, sert à d'autres jeux
et n'appartient pas à ce projet. Le venv non plus — on tourne *depuis* lui ;
c'est `install.sh --uninstall` qui s'en charge, après nous.

Ce module ne fait qu'établir un **plan** (`build_plan`) puis l'appliquer
(`apply_plan`) : la séparation rend le tout testable sans rien effacer, et
permet d'afficher exactement ce qui va disparaître avant de le faire.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import logging_setup, state
from stalker_gamma_linux.desktop.paths import DesktopPaths
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _


@dataclass(frozen=True, slots=True)
class Removal:
    """Un élément à retirer, avec de quoi l'expliquer à l'utilisateur."""

    path: Path
    label: str
    # Les données de jeu ne partent qu'avec `--game-data` : on veut pouvoir les
    # distinguer dans le plan pour les annoncer différemment.
    is_game_data: bool = False

    @property
    def exists(self) -> bool:
        # `is_symlink` d'abord : un lien cassé (venv déjà supprimé) doit rester
        # détectable, alors que `exists()` suit le lien et répond False.
        return self.path.is_symlink() or self.path.exists()


@dataclass(frozen=True, slots=True)
class UninstallPlan:
    removals: tuple[Removal, ...]

    @property
    def present(self) -> tuple[Removal, ...]:
        """Uniquement ce qui existe réellement — le reste n'a pas à être affiché."""
        return tuple(removal for removal in self.removals if removal.exists)

    @property
    def is_empty(self) -> bool:
        return not self.present


def _local_bin() -> Path:
    return Path.home() / ".local" / "bin"


def build_plan(
    target: Path | None = None,
    *,
    game_data: bool = False,
    desktop: DesktopPaths | None = None,
) -> UninstallPlan:
    """Liste ce qui serait retiré. N'efface rien, ne touche pas au disque."""
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    paths = desktop if desktop is not None else DesktopPaths.default()

    removals = [
        Removal(paths.desktop_file, _("desktop entry (« Play GAMMA (direct) »)")),
        Removal(
            paths.applications_dir / "stalker-gamma-linux-gui.desktop",
            _("desktop entry (« GAMMA Linux Launcher »)"),
        ),
        Removal(paths.icon_file, _("application icon")),
        Removal(
            paths.icon_theme_root / "512x512" / "apps" / "stalker-gamma-linux-gui.png",
            _("launcher icon"),
        ),
        Removal(_local_bin() / "stalker-gamma-linux", _("`stalker-gamma-linux` command")),
        Removal(_local_bin() / "stalker-gamma-linux-gui", _("`stalker-gamma-linux-gui` command")),
        Removal(state.config_dir(), _("settings and install state")),
        Removal(logging_setup.state_dir(), _("logs")),
    ]
    if game_data:
        removals.append(
            Removal(root, _("game data (Anomaly, mods, cache, Proton prefix)"), is_game_data=True)
        )
    return UninstallPlan(removals=tuple(removals))


def apply_plan(plan: UninstallPlan) -> tuple[Removal, ...]:
    """Retire tout ce que le plan désigne. Retourne ce qui a effectivement disparu.

    Une suppression qui échoue (permissions, montage occupé) n'interrompt pas
    les suivantes : mieux vaut un nettoyage partiel qu'un abandon à mi-chemin,
    et le résultat retourné dit exactement ce qui est parti.
    """
    removed: list[Removal] = []
    for removal in plan.present:
        try:
            if removal.path.is_symlink() or removal.path.is_file():
                removal.path.unlink()
            else:
                shutil.rmtree(removal.path)
        except OSError:
            continue
        removed.append(removal)
    return tuple(removed)


def format_plan(plan: UninstallPlan) -> str:
    lines = [_("The following will be removed:"), ""]
    lines.extend(f"  - {removal.label}\n      {removal.path}" for removal in plan.present)
    return "\n".join(lines)


def format_removed(removed: Sequence[Removal]) -> str:
    if not removed:
        return _("Nothing to remove — already clean.")
    lines = [_("Removed:"), ""]
    lines.extend(f"  - {removal.label}" for removal in removed)
    return "\n".join(lines)


def run_uninstall(
    target: Path | None = None,
    *,
    game_data: bool = False,
    dry_run: bool = False,
    venv_hint: bool = True,
) -> int:
    """Commande CLI `uninstall`. Retourne 0 même s'il n'y avait rien à faire.

    `venv_hint=False` quand `install.sh --uninstall` nous appelle : il retire le
    venv lui-même juste après, et lui dire « il est toujours là, supprimez-le à
    la main » serait faux.
    """
    from stalker_gamma_linux import output

    root = target if target is not None else DEFAULT_INSTALL_TARGET
    plan = build_plan(root, game_data=game_data)

    if plan.is_empty:
        output.success(_("Nothing to remove — already clean."))
        return 0

    if dry_run:
        output.header(_("Dry run — nothing will be deleted."))
        output.progress(format_plan(plan))
        return 0

    output.progress(format_removed(apply_plan(plan)))
    if not game_data:
        # Le chemin est affiché même si le dossier n'existe pas : c'est une
        # information, pas une injonction — et il vaut mieux le donner que
        # laisser l'utilisateur chercher où sont passés ses 146 Gio.
        output.warn(
            _(
                "\nGame data was kept: {root}\n"
                "Remove it with `--game-data`, or delete that directory by hand."
            ).format(root=root)
        )
    if venv_hint:
        output.success(
            _(
                "\nThe Python environment itself (~/.local/share/stalker-gamma-linux/venv) "
                "is still there — this command runs from it. Remove it with:\n"
                "  rm -rf ~/.local/share/stalker-gamma-linux"
            )
        )
    return 0
