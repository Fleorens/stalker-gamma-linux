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

import os
import tomllib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import tomli_w

STEPS: tuple[str, ...] = ("anomaly", "gamma", "reshade", "prefix", "mo2", "shortcut")

STEP_LABELS: dict[str, str] = {
    "anomaly": "Anomaly (jeu de base)",
    "gamma": "Modpack G.A.M.M.A (mods + instance MO2)",
    "reshade": "Retrait de ReShade + purge du cache de shaders",
    "prefix": "Préfixe Proton partagé",
    "mo2": "Configuration de l'instance Mod Organizer 2",
    "shortcut": "Raccourci bureau",
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


def _load_raw() -> dict[str, dict[str, object]]:
    try:
        text = state_file().read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
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
        raise ValueError(f"étape inconnue : {step}")
    installs = _load_raw()
    key = _target_key(target)
    entry = dict(installs.get(key, {}))
    entry[step] = True
    entry["updated_at"] = datetime.now(UTC).isoformat()
    installs[key] = entry
    _save_raw(installs)
    return load_state(target)


def format_state(state: InstallState, target: Path) -> str:
    lines = [f"Cible : {target}", ""]
    for step in STEPS:
        label = "[ OK ]" if state.is_done(step) else "[ A FAIRE ]"
        lines.append(f"{label} {STEP_LABELS[step]}")
    return "\n".join(lines)
