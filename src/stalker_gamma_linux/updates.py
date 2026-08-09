"""Vérification **en lecture seule** de la disponibilité d'une mise à jour GAMMA.

Ce module existe à cause d'un bug de conception : l'entrée de menu
« Check for updates » lançait `run_update`, c'est-à-dire un `full-install`
complet. Un bouton qui annonce une vérification doit vérifier, pas réinstaller
— d'autant que `full-install` **écrase** `profiles/G.A.M.M.A/modlist.txt` avec
la liste amont, donc les mods activés/désactivés et l'ordre de chargement de
l'utilisateur (constaté sur une vraie install : 757 lignes personnalisées
contre 752 en amont).

La vérification compare les fichiers de définition du modpack — `modlist.txt`
et `modpack_maker_list.txt`, quelques dizaines de Ko — entre la copie locale
(déposée par la dernière installation sous `.Grok's Modpack Installer/`) et
celle publiée sur GitHub. C'est exactement ce que fait déjà
`scripts/upstream_smoke_test.py`, sans rien télécharger d'autre et sans jamais
écrire sur le disque.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix.download import read_remote_bytes

UPSTREAM_REPO = "Grokitach/Stalker_GAMMA"
UPSTREAM_REF = "main"
_RAW_BASE = "https://raw.githubusercontent.com"

# Déposé par gamma-launcher lors de l'installation, à l'intérieur de `<gamma>`.
_MODPACK_DATA_DIR = Path(".Grok's Modpack Installer") / "G.A.M.M.A" / "modpack_data"

# Les deux fichiers qui décrivent le modpack : la liste des mods et leurs
# directives d'installation. Si aucun des deux n'a bougé, rien n'a changé.
DEFINITION_FILES = ("modlist.txt", "modpack_maker_list.txt")


class UpdateStatus(Enum):
    UP_TO_DATE = auto()
    AVAILABLE = auto()
    # Impossible de conclure : réseau coupé, ou aucune copie locale à comparer
    # (installation faite hors pipeline). On ne prétend jamais « à jour ».
    UNKNOWN = auto()


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    status: UpdateStatus
    changed: tuple[str, ...] = ()
    detail: str = ""

    @property
    def is_available(self) -> bool:
        return self.status is UpdateStatus.AVAILABLE

    @property
    def message(self) -> str:
        if self.status is UpdateStatus.UP_TO_DATE:
            return _("Your modpack is up to date with upstream G.A.M.M.A.")
        if self.status is UpdateStatus.AVAILABLE:
            return _(
                "An update is available: {files} changed upstream.\n"
                "Updating re-downloads only what changed."
            ).format(files=", ".join(self.changed))
        return _("Could not check for updates: {detail}").format(detail=self.detail)


def local_definition_dir(gamma_dir: Path) -> Path:
    return gamma_dir / _MODPACK_DATA_DIR


def _digest(payload: bytes) -> str:
    # Les fins de ligne diffèrent entre le dépôt (LF) et la copie locale
    # (CRLF selon l'extraction) : comparer le contenu normalisé, pas les octets.
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def _upstream_url(filename: str, repo: str, ref: str) -> str:
    return f"{_RAW_BASE}/{repo}/{ref}/G.A.M.M.A/modpack_data/{filename}"


def check_for_updates(
    gamma_dir: Path, *, repo: str = UPSTREAM_REPO, ref: str = UPSTREAM_REF
) -> UpdateCheck:
    """Compare les définitions locales du modpack à celles publiées. N'écrit rien."""
    definitions = local_definition_dir(gamma_dir)
    if not definitions.is_dir():
        return UpdateCheck(
            status=UpdateStatus.UNKNOWN,
            detail=_("no local modpack definition found at {path}").format(path=definitions),
        )

    changed: list[str] = []
    for filename in DEFINITION_FILES:
        local = definitions / filename
        if not local.is_file():
            return UpdateCheck(
                status=UpdateStatus.UNKNOWN,
                detail=_("{filename} is missing locally").format(filename=filename),
            )
        try:
            remote = read_remote_bytes(_upstream_url(filename, repo, ref))
        except OSError as error:
            return UpdateCheck(status=UpdateStatus.UNKNOWN, detail=str(error))
        if _digest(remote) != _digest(local.read_bytes()):
            changed.append(filename)

    if changed:
        return UpdateCheck(status=UpdateStatus.AVAILABLE, changed=tuple(changed))
    return UpdateCheck(status=UpdateStatus.UP_TO_DATE)


def run_update_check(target: Path | None = None) -> int:
    """Commande `update --check` : vérifie, n'installe rien. 0 si à jour, 1 sinon."""
    from stalker_gamma_linux import output
    from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
    from stalker_gamma_linux.mo2.paths import Mo2Paths

    root = target if target is not None else DEFAULT_INSTALL_TARGET
    result = check_for_updates(Mo2Paths.under(root).instance)

    if result.status is UpdateStatus.UP_TO_DATE:
        output.success(result.message)
        return 0
    if result.is_available:
        output.warn(result.message)
        output.progress(
            _(
                "Run `stalker-gamma-linux update` to apply it. Note: this resets "
                "the MO2 mod list to the upstream one (a backup is written first)."
            )
        )
        return 1
    output.error(result.message)
    return 1
