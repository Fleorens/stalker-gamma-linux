"""État persisté de l'installation (reprise après interruption, commande `install`).

Chaque étape du pipeline (`anomaly`, `gamma`, `reshade`, `prefix`, `mo2`,
`shortcut`) est déjà idempotente côté module (voir docs/ARCHITECTURE.md) :
relancer `install` sans cet état serait donc déjà correct, mais coûteux (une
re-vérification MD5 complète du modpack à chaque relance). Ce module se
contente d'un raccourci — sauter une étape déjà marquée faite — persisté en
TOML sous `~/.config/stalker-gamma-linux/` (XDG). Ce n'est pas la source de
vérité de santé de l'installation (`prefix-doctor`/`doctor` le sont) : si une
étape est altérée manuellement après coup, c'est `update`/`prefix-doctor
--repair` qui la corrige, pas une invalidation automatique ici.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import tomli_w

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.logging_setup import LOGGER_NAME

_logger = logging.getLogger(LOGGER_NAME)

STEPS: tuple[str, ...] = ("anomaly", "gamma", "reshade", "prefix", "mo2", "shortcut")

STEP_LABELS: dict[str, str] = {
    "anomaly": _("Anomaly (base game)"),
    "gamma": _("G.A.M.M.A modpack (mods + MO2 instance)"),
    "reshade": _("Removing ReShade + purging the shader cache"),
    "prefix": _("Shared Proton prefix"),
    "mo2": _("Mod Organizer 2 instance configuration"),
    "shortcut": _("Desktop shortcut"),
}


@dataclass(frozen=True, slots=True)
class InstallState:
    """Étapes du pipeline `install` déjà validées pour une cible donnée."""

    anomaly: bool = False
    gamma: bool = False
    reshade: bool = False
    prefix: bool = False
    mo2: bool = False
    shortcut: bool = False

    def is_done(self, step: str) -> bool:
        return bool(getattr(self, step))

    def with_done(self, step: str) -> InstallState:
        return replace(self, **{step: True})


def config_dir() -> Path:
    """`$XDG_CONFIG_HOME`, ou `~/.config` par défaut (spec freedesktop)."""
    override = os.environ.get("XDG_CONFIG_HOME")
    base = Path(override) if override else Path.home() / ".config"
    return base / "stalker-gamma-linux"


def state_file() -> Path:
    return config_dir() / "install-state.toml"


def _target_key(target: Path) -> str:
    return str(target.resolve())


def _quarantine_corrupt_state(error: tomllib.TOMLDecodeError) -> None:
    """Met de côté un `install-state.toml` illisible au lieu de l'écraser en silence.

    Repartir d'un état vide est le bon comportement fonctionnel (une étape
    perdue est seulement rejouée), mais le prochain `mark_done` réécrit le
    fichier : sans ce déplacement, la progression de **toutes** les cibles
    disparaissait sans trace, et l'utilisateur subissait une re-vérification MD5
    complète du modpack sans savoir pourquoi.
    """
    path = state_file()
    quarantined = path.with_suffix(f"{path.suffix}.corrupt")
    try:
        path.replace(quarantined)
    except OSError as move_error:
        _logger.warning("could not quarantine corrupt state file %s: %s", path, move_error)
        return
    _logger.warning(
        "state file %s was unreadable (%s); moved to %s and starting from an empty state — "
        "already-installed steps will simply be replayed",
        path,
        error,
        quarantined,
    )


def _load_raw() -> dict[str, dict[str, object]]:
    try:
        text = state_file().read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}  # première exécution : absence normale, rien à signaler
    except OSError as error:
        _logger.warning("could not read state file %s: %s", state_file(), error)
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        _quarantine_corrupt_state(error)
        return {}
    installs = data.get("installs", {})
    return installs if isinstance(installs, dict) else {}


def _save_raw(installs: dict[str, dict[str, object]]) -> None:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    state_file().write_text(tomli_w.dumps({"installs": installs}), encoding="utf-8")


def load_state(target: Path) -> InstallState:
    """État persisté pour `target`, ou l'état par défaut (rien de fait) si absent/corrompu."""
    entry = _load_raw().get(_target_key(target), {})
    return InstallState(**{step: bool(entry.get(step, False)) for step in STEPS})


def mark_done(target: Path, step: str) -> InstallState:
    """Marque `step` comme fait pour `target` et persiste. Retourne le nouvel état."""
    if step not in STEPS:
        raise ValueError(_("unknown step: {step}").format(step=step))
    installs = _load_raw()
    key = _target_key(target)
    entry = dict(installs.get(key, {}))
    entry[step] = True
    entry["updated_at"] = datetime.now(UTC).isoformat()
    installs[key] = entry
    _save_raw(installs)
    return load_state(target)


def format_state(state: InstallState, target: Path) -> str:
    lines = [_("Target: {target}").format(target=target), ""]
    for step in STEPS:
        label = _("[ OK ]") if state.is_done(step) else _("[ TODO ]")
        lines.append(f"{label} {STEP_LABELS[step]}")
    return "\n".join(lines)
