"""État persisté de l'installation (reprise après interruption, commande `install`).

Chaque étape du pipeline (`anomaly`, `gamma`, `reshade`, `prefix`, `mo2`,
`shortcut`, `steam`) est déjà idempotente côté module (voir docs/ARCHITECTURE.md) :
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

STEPS: tuple[str, ...] = ("anomaly", "gamma", "reshade", "prefix", "mo2", "shortcut", "steam")

# Étapes que `install` ne joue que si on les lui demande — leur absence ne rend
# pas une installation incomplète (voir `gui.viewmodel`).
OPTIONAL_STEPS: tuple[str, ...] = ("shortcut", "steam")


def planned_steps(*, shortcut: bool, steam: bool) -> tuple[str, ...]:
    """Étapes qu'`install` jouera, dans l'ordre — les optionnelles seulement si demandées.

    Source unique de la numérotation « n/total » : l'orchestrateur et la barre
    de progression de la GUI la lisent tous les deux ici, au lieu de la
    redériver chacun de son côté (c'est ce que faisait un `STEPS[:-1]`, qui
    cassait dès qu'une seconde étape optionnelle est apparue).
    """
    wanted = {"shortcut": shortcut, "steam": steam}
    return tuple(step for step in STEPS if wanted.get(step, True))


STEP_LABELS: dict[str, str] = {
    "anomaly": _("Anomaly (base game)"),
    "gamma": _("G.A.M.M.A modpack (mods + MO2 instance)"),
    "reshade": _("Removing ReShade + purging the shader cache"),
    "prefix": _("Shared Proton prefix"),
    "mo2": _("Mod Organizer 2 instance configuration"),
    "shortcut": _("Desktop shortcut"),
    "steam": _("Steam library entry (artwork included)"),
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
    steam: bool = False

    def is_done(self, step: str) -> bool:
        return bool(getattr(self, step))

    def with_done(self, step: str) -> InstallState:
        return replace(self, **{step: True})


@dataclass(frozen=True, slots=True)
class FailedMod:
    """Un mod dont le téléchargement/installation a échoué (T22).

    `cause` est le nom du `engine.markers.FailureCause` reconnu (ou `"unknown"`
    si `EngineExecutionError` n'a rien classé) — stocké en texte, pas en objet,
    puisque c'est écrit tel quel dans le TOML persisté. `detail` est le message
    complet de l'erreur d'origine (déjà actionnable, hint compris) : c'est lui
    qu'un utilisateur colle dans une issue. `archive_name`/`expected_md5`
    (chaîne vide si inconnus — TOML n'a pas de `None`) alimentent la
    vérification du fichier déposé à la main par `orchestrator.run_retry_failed`.
    """

    name: str
    cause: str
    detail: str
    recorded_at: str
    archive_name: str = ""
    expected_md5: str = ""


def record_failure(target: Path, failure: FailedMod) -> None:
    """Enregistre (ou remplace) l'échec de `failure.name` pour `target`.

    Un nouvel enregistrement du même mod écrase le précédent — c'est la cause
    la plus récente qui compte, pas l'historique de ses échecs successifs.
    """
    installs = _load_raw()
    key = _target_key(target)
    entry = dict(installs.get(key, {}))
    failed = [row for row in _failed_rows(entry) if row.get("name") != failure.name]
    failed.append(
        {
            "name": failure.name,
            "cause": failure.cause,
            "detail": failure.detail,
            "recorded_at": failure.recorded_at,
            "archive_name": failure.archive_name,
            "expected_md5": failure.expected_md5,
        }
    )
    entry["failed_mods"] = failed
    installs[key] = entry
    _save_raw(installs)


def load_failures(target: Path) -> tuple[FailedMod, ...]:
    """Échecs actuellement enregistrés pour `target`, dans l'ordre d'enregistrement."""
    entry = _load_raw().get(_target_key(target), {})
    return tuple(
        FailedMod(
            name=str(row.get("name", "")),
            cause=str(row.get("cause", "unknown")),
            detail=str(row.get("detail", "")),
            recorded_at=str(row.get("recorded_at", "")),
            archive_name=str(row.get("archive_name", "")),
            expected_md5=str(row.get("expected_md5", "")),
        )
        for row in _failed_rows(entry)
    )


def clear_failure(target: Path, name: str) -> None:
    """Retire `name` des échecs enregistrés — appelé après une reprise réussie.

    Silencieux si `name` n'y était pas : `install --retry-failed` l'appelle
    pour chaque mod qu'il vient de réinstaller sans savoir lesquels ont
    réellement échoué avant lui.
    """
    installs = _load_raw()
    key = _target_key(target)
    entry = dict(installs.get(key, {}))
    remaining = [row for row in _failed_rows(entry) if row.get("name") != name]
    if len(remaining) == len(_failed_rows(entry)):
        return
    entry["failed_mods"] = remaining
    installs[key] = entry
    _save_raw(installs)


def clear_all_failures(target: Path) -> None:
    """Vide la liste des échecs enregistrés pour `target`.

    Appelé quand `full-install` vient de parcourir tout le modpack sans lever
    — la preuve la plus directe que plus aucun mod n'est en échec, même si un
    échec plus ancien traînait encore dans l'état persisté.
    """
    installs = _load_raw()
    key = _target_key(target)
    entry = dict(installs.get(key, {}))
    if not _failed_rows(entry):
        return
    entry["failed_mods"] = []
    installs[key] = entry
    _save_raw(installs)


def _failed_rows(entry: dict[str, object]) -> list[dict[str, object]]:
    rows = entry.get("failed_mods", [])
    return list(rows) if isinstance(rows, list) else []


def format_failures(failures: tuple[FailedMod, ...]) -> str:
    """Rendu texte des échecs enregistrés — le « compte rendu honnête » de fin d'install."""
    if not failures:
        return ""
    lines = [
        _(
            "{count} mod(s) with a known unresolved failure — everything else "
            "already installed is untouched:"
        ).format(count=len(failures))
    ]
    lines.extend(f"  - {failure.name} ({failure.cause})" for failure in failures)
    lines.append(_("Run `stalker-gamma-linux install --retry-failed` once addressed."))
    return "\n".join(lines)


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
