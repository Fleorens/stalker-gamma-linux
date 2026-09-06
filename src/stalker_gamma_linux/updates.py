"""Vérification **en lecture seule** de la disponibilité d'une mise à jour GAMMA.

Ce module existe à cause d'un bug de conception : l'entrée de menu
« Check for updates » lançait `run_update`, c'est-à-dire un `full-install`
complet. Un bouton qui annonce une vérification doit vérifier, pas réinstaller
— d'autant que `full-install` **écrase** `profiles/G.A.M.M.A/modlist.txt` avec
la liste amont, donc les mods activés/désactivés et l'ordre de chargement de
l'utilisateur (constaté sur une vraie install : 757 lignes personnalisées
contre 752 en amont).

**Sur quoi on se base.** Grokitach publie `G.A.M.M.A_definition_version.txt`
à la racine de son dépôt : c'est *son* numéro de définition de modpack (920 au
2026-08-09), celui qui change quand le contenu du modpack change. C'est donc le
signal qui fait autorité, et il est comparé en priorité.

On y ajoute `modlist.txt` et `modpack_maker_list.txt` — la liste des mods et
leurs directives d'installation — pour couvrir le cas d'une définition modifiée
sans que le numéro soit incrémenté. Trois fichiers, quelques dizaines de Ko au
total.

Tout passe par `raw.githubusercontent.com`, jamais par l'API GitHub : celle-ci
est limitée à 60 requêtes/h sans authentification, ce qui transformerait un
clic répété sur « Vérifier » en faux « indéterminé ».

Ce qu'on ne détecte **pas** : une archive de mod mise à jour sur ModDB sans que
Grokitach touche à ses définitions. Ce cas-là n'apparaît qu'au moment d'un vrai
`update`. En sens inverse, la copie locale vient de la dernière installation
faite par le pipeline — sans elle (install posée à la main), on répond
« indéterminé » plutôt que d'inventer une réponse.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix.download import read_remote_bytes

UPSTREAM_REPO = "Grokitach/Stalker_GAMMA"
UPSTREAM_REF = "main"
_RAW_BASE = "https://raw.githubusercontent.com"

# Déposé par gamma-launcher lors de l'installation, à l'intérieur de `<gamma>`.
_INSTALLER_DIR = Path(".Grok's Modpack Installer")
_MODPACK_DATA_DIR = _INSTALLER_DIR / "G.A.M.M.A" / "modpack_data"
# Mods livrés en clair par le modpack, copiés tels quels dans `mods/` par
# `FullInstall._copy_gamma_modpack` — ils ne figurent pas dans `modlist.txt`.
_MODPACK_ADDONS_DIR = _INSTALLER_DIR / "G.A.M.M.A" / "modpack_addons"

# Numéro de définition publié par Grokitach : le signal qui fait autorité.
VERSION_FILE = "G.A.M.M.A_definition_version.txt"

# Définitions du modpack : liste des mods et directives d'installation. Filet
# pour le cas d'une définition modifiée sans incrément du numéro ci-dessus.
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

    # Numéros de définition GAMMA, quand ils ont pu être lus (« 920 »).
    local_version: str = ""
    upstream_version: str = ""

    @property
    def message(self) -> str:
        if self.status is UpdateStatus.UP_TO_DATE:
            if self.local_version:
                return _("Your modpack is up to date (G.A.M.M.A definition {version}).").format(
                    version=self.local_version
                )
            return _("Your modpack is up to date with upstream G.A.M.M.A.")
        if self.status is UpdateStatus.AVAILABLE:
            if self.local_version and self.upstream_version != self.local_version:
                return _(
                    "An update is available: G.A.M.M.A definition {local} → {upstream}.\n"
                    "Updating re-downloads only what changed."
                ).format(local=self.local_version, upstream=self.upstream_version)
            return _(
                "An update is available: {files} changed upstream.\n"
                "Updating re-downloads only what changed."
            ).format(files=", ".join(self.changed))
        return _("Could not check for updates: {detail}").format(detail=self.detail)


def local_definition_dir(gamma_dir: Path) -> Path:
    return gamma_dir / _MODPACK_DATA_DIR


def local_addons_dir(gamma_dir: Path) -> Path:
    """Dossier des mods livrés en clair par le modpack (voir `_MODPACK_ADDONS_DIR`)."""
    return gamma_dir / _MODPACK_ADDONS_DIR


def local_version_file(gamma_dir: Path) -> Path:
    return gamma_dir / _INSTALLER_DIR / VERSION_FILE


def _digest(payload: bytes) -> str:
    # Les fins de ligne diffèrent entre le dépôt (LF) et la copie locale
    # (CRLF selon l'extraction) : comparer le contenu normalisé, pas les octets.
    return hashlib.sha256(payload.replace(b"\r\n", b"\n")).hexdigest()


def _upstream_url(filename: str, repo: str, ref: str) -> str:
    return f"{_RAW_BASE}/{repo}/{ref}/G.A.M.M.A/modpack_data/{filename}"


def _upstream_version_url(repo: str, ref: str) -> str:
    return f"{_RAW_BASE}/{repo}/{ref}/{VERSION_FILE}"


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

    # 1. Le numéro de définition publié par Grokitach — le signal qui fait foi.
    local_version = upstream_version = ""
    version_path = local_version_file(gamma_dir)
    if version_path.is_file():
        local_version = version_path.read_text(encoding="utf-8", errors="replace").strip()
        try:
            upstream_version = (
                read_remote_bytes(_upstream_version_url(repo, ref)).decode("utf-8").strip()
            )
        except OSError as error:
            return UpdateCheck(status=UpdateStatus.UNKNOWN, detail=str(error))
        if upstream_version and upstream_version != local_version:
            return UpdateCheck(
                status=UpdateStatus.AVAILABLE,
                changed=(VERSION_FILE,),
                local_version=local_version,
                upstream_version=upstream_version,
            )

    # 2. Filet : une définition modifiée sans incrément du numéro. Les deux
    # fichiers sont indépendants l'un de l'autre : on lance les deux requêtes
    # en parallèle pour ne payer qu'une fois la latence réseau (poignée TCP +
    # TLS) au lieu de l'une après l'autre.
    for filename in DEFINITION_FILES:
        if not (definitions / filename).is_file():
            return UpdateCheck(
                status=UpdateStatus.UNKNOWN,
                detail=_("{filename} is missing locally").format(filename=filename),
            )

    try:
        with ThreadPoolExecutor(max_workers=len(DEFINITION_FILES)) as executor:
            futures: dict[str, Future[bytes]] = {
                filename: executor.submit(read_remote_bytes, _upstream_url(filename, repo, ref))
                for filename in DEFINITION_FILES
            }
            remotes = {filename: future.result() for filename, future in futures.items()}
    except OSError as error:
        return UpdateCheck(status=UpdateStatus.UNKNOWN, detail=str(error))

    # Ordre de DEFINITION_FILES, pas celui d'achèvement des requêtes.
    changed = [
        filename
        for filename in DEFINITION_FILES
        if _digest(remotes[filename]) != _digest((definitions / filename).read_bytes())
    ]

    if changed:
        return UpdateCheck(
            status=UpdateStatus.AVAILABLE,
            changed=tuple(changed),
            local_version=local_version,
            upstream_version=upstream_version,
        )
    return UpdateCheck(
        status=UpdateStatus.UP_TO_DATE,
        local_version=local_version,
        upstream_version=upstream_version,
    )


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
