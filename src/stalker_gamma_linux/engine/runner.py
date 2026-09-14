"""Fonctions de haut niveau pilotant gamma-launcher : install/update/verify.

Aucune logique de résolution ModDB, de parsing de modlist ou d'extraction
n'est réimplémentée ici : tout est délégué au binaire `gamma-launcher` via
`stalker_gamma_linux.engine.process.run` (voir docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from stalker_gamma_linux.engine import markers
from stalker_gamma_linux.engine.errors import EngineExecutionError, VerificationError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.engine.process import ProgressCallback, run

# `launcher/commands/install.py:_install_mods` :
# `print(f'[+] Processing mod {mod.info.title or mod.info.name} ({i}/{mods_len})')`
# — seule trace du mod en cours dans le flux ; rien d'équivalent n'existe côté
# `AttributeError`/`ModDBDownloadError` eux-mêmes.
_PROCESSING_MOD_RE = re.compile(r"^\[\+\] Processing mod (?P<name>.+) \(\d+/\d+\)$")

# `launcher/hash.py:check_hash` : `tqdm(desc=f"Calculating hash of {file.name}", ...)`
# — imprimé juste avant qu'une archive en cache soit (re)vérifiée, donc juste
# avant qu'une extraction sur une archive corrompue échoue (issues #283/#284).
_HASHING_FILE_RE = re.compile(r"^Calculating hash of (?P<filename>.+?): ")

# Best-effort : rien dans la sortie actuelle de gamma-launcher n'imprime le MD5
# attendu (`ModDBDownloader._parse_moddb_metadata` le garde pour elle-même). Ce
# motif ne sert donc à rien aujourd'hui, mais coûte peu et couvre une version
# amont future — ou un outil tiers — qui l'afficherait sous une forme usuelle
# (« MD5 Hash: <32 hex> », le nom du champ tel que lu sur la page ModDB).
_MD5_HINT_RE = re.compile(r"MD5(?:\s*Hash)?\s*[:=]\s*([0-9a-fA-F]{32})\b", re.IGNORECASE)


def _gamma_downloads(paths: InstallPaths) -> Path:
    """Dossier de dépôt des archives de mods (`InstallPaths.downloads`).

    C'est bien celui-ci qu'il faut nommer à l'utilisateur pour un dépôt
    manuel — pas `cache/`, que cette sous-commande n'utilise pas (on ne lui
    passe volontairement pas `--cache-directory`, voir `install_gamma`).
    """
    return paths.downloads


def _extract_tmpdir(paths: InstallPaths) -> Path:
    """Dossier temporaire d'extraction, sur le disque d'installation.

    gamma-launcher extrait chaque archive dans `TMPDIR` (`/tmp` par défaut).
    Sur Linux `/tmp` est presque toujours un tmpfs **en RAM** (défaut Fedora,
    plafonné à ~50 % de la RAM) : les archives multi-Go de GAMMA le saturent
    (`OSError` ENOSPC/EDQUOT). On le place sous `cache/` — même système de
    fichiers que `mods/`, donc de la place et un déplacement final local. Voir
    `engine.process._engine_environment`.
    """
    return paths.cache / "tmp"


def _install(
    subcommand: str,
    args: list[str],
    *,
    on_progress: ProgressCallback | None,
    cancel_event: threading.Event | None,
    tmpdir: Path,
    download_dir: Path,
) -> None:
    """Lance `anomaly-install`/`full-install` en suivant en direct le mod en cours.

    Sert uniquement à enrichir une éventuelle `EngineExecutionError` avec le
    nom du mod et le fichier concernés (voir son docstring) : `output_tail` (20
    dernières lignes retenues par `engine.process.run`) ne les contient pas
    forcément, une trace Python longue les poussant dehors. Ce suivi doit donc
    voir **tout** le flux, pas seulement sa queue — d'où ce wrapper, plutôt
    qu'une reclassification a posteriori sur `output_tail`.
    """
    progress = on_progress or (lambda _line: None)
    seen: dict[str, str | None] = {"mod": None, "archive": None, "md5": None}

    def watch(line: str) -> None:
        stripped = line.strip()
        mod_match = _PROCESSING_MOD_RE.match(stripped)
        if mod_match:
            seen["mod"] = mod_match.group("name")
        archive_match = _HASHING_FILE_RE.match(stripped)
        if archive_match:
            seen["archive"] = archive_match.group("filename")
        md5_match = _MD5_HINT_RE.search(stripped)
        if md5_match:
            seen["md5"] = md5_match.group(1)
        progress(line)

    try:
        run(
            subcommand,
            args,
            on_progress=watch,
            cancel_event=cancel_event,
            tmpdir=tmpdir,
            download_dir=download_dir,
        )
    except EngineExecutionError as error:
        if seen["mod"] is None and seen["archive"] is None and seen["md5"] is None:
            raise
        raise EngineExecutionError(
            error.subcommand,
            error.returncode,
            error.output_tail,
            error.download_dir,
            mod_name=seen["mod"],
            archive_name=seen["archive"],
            expected_md5=seen["md5"],
        ) from error


def install_anomaly(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Installe S.T.A.L.K.E.R.: Anomaly (`gamma-launcher anomaly-install`)."""
    paths.ensure_directories()
    _install(
        "anomaly-install",
        ["--anomaly", str(paths.anomaly), "--cache-directory", str(paths.cache)],
        on_progress=on_progress,
        cancel_event=cancel_event,
        tmpdir=_extract_tmpdir(paths),
        download_dir=paths.cache,
    )


def install_gamma(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Installe (ou met à jour) le modpack G.A.M.M.A. (`gamma-launcher full-install`).

    `full-install` est idempotent côté gamma-launcher : rejoué sur une
    installation existante, il ne fait que la mettre à jour — voir
    `update_gamma`, qui appelle exactement cette même fonction.

    On ne passe **volontairement pas** `--cache-directory` ici (contrairement à
    `install_anomaly`). En sa présence, `GammaSetup` remplace `<gamma>/downloads`
    par un lien symbolique vers le cache (`downloads.rmdir()` puis
    `symlink_to(...)`) ; rejoué sur une install existante, ce `rmdir()` s'exécute
    sur le lien déjà en place et lève `NotADirectoryError` (errno 20 : rmdir
    refuse un lien symbolique) — la mise à jour plantait toujours ainsi. Sans
    cache-directory, gamma-launcher saute entièrement ce bloc : le crash devient
    impossible, `<gamma>/downloads` reste un vrai dossier (ou le lien existant,
    qu'il suit sans le toucher), et les téléchargements y persistent d'une
    relance à l'autre — aucun re-téléchargement. Le gros cache utile (l'archive
    de base Anomaly) reste couvert par `install_anomaly`.

    On passe `--preserve-user-config` dès qu'un `appdata/user.ltx` existe déjà.
    Sinon, `_patch_anomaly` écrase les réglages joueur (graphismes, contrôles,
    gameplay) par la config par défaut du modpack — une mise à jour ne doit pas
    reset les réglages. Sur une install fraîche, `user.ltx` n'existe pas encore :
    on ne passe pas le drapeau (gamma-launcher planterait à restaurer un `.bak`
    inexistant, et il n'y a de toute façon rien à préserver).
    """
    paths.ensure_directories()
    args = ["--anomaly", str(paths.anomaly), "--gamma", str(paths.gamma)]
    if (paths.anomaly / "appdata" / "user.ltx").is_file():
        args.append("--preserve-user-config")
    _install(
        "full-install",
        args,
        on_progress=on_progress,
        cancel_event=cancel_event,
        tmpdir=_extract_tmpdir(paths),
        download_dir=_gamma_downloads(paths),
    )


def update_gamma(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Alias de `install_gamma`.

    gamma-launcher v3.1 n'expose pas de sous-commande `update` séparée :
    `full-install` sert aux deux usages (voir docs/ARCHITECTURE.md).
    """
    install_gamma(paths, on_progress=on_progress, cancel_event=cancel_event)


def remove_reshade(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Retire ReShade, incompatible DXVK/Proton (`gamma-launcher remove-reshade`).

    Étape **obligatoire** avant de jouer (docs/INSTALL-MANUAL.md §5) : ReShade,
    injecté par le modpack pour Windows, casse le rendu ou le lancement sous DXVK.
    """
    run(
        "remove-reshade",
        ["--anomaly", str(paths.anomaly)],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def purge_shader_cache(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Vide le cache de shaders d'Anomaly (`gamma-launcher purge-shader-cache`).

    Complète `remove_reshade` : un cache obsolète après retrait de ReShade ou
    après une mise à jour provoque des artefacts (docs/INSTALL-MANUAL.md §5, §9).

    C'est le cache **X-Ray** (celui d'Anomaly) — `--anomaly` et rien d'autre.
    Sans rapport avec le cache DXVK/Mesa/NVIDIA sous `cache/shaders/`
    (`environment.shader_cache`, T21) : celui-là, on ne le purge jamais ici.
    """
    run(
        "purge-shader-cache",
        ["--anomaly", str(paths.anomaly)],
        on_progress=on_progress,
        cancel_event=cancel_event,
    )


def verify(
    paths: InstallPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str, ...]:
    """Vérifie l'intégrité des archives de mods (`check-md5`).

    Retourne les lignes « invérifiables en ligne » (ModDB illisible ou version
    amont qui a dérivé — voir `engine.markers.UNVERIFIABLE_MARKERS`) : les
    archives locales correspondantes n'ont **pas** pu être comparées à leur
    somme amont, mais rien n'indique une corruption — à présenter comme
    avertissement. Lève `VerificationError` si une archive locale est
    réellement corrompue ou manquante (`Hash verification failed`), ou si
    `check-md5` échoue pour une raison inconnue.

    On ne lance **pas** `check-anomaly` ici. Il compare les fichiers d'Anomaly
    aux sommes de contrôle *vanilla* (`tools/checksums.md5`), or une install
    GAMMA patche volontairement `bin/*.exe` et `fsgame.ltx` : lancé après le
    patch il échoue donc toujours sur ces fichiers (faux négatif). gamma-launcher
    le documente lui-même (« Only works if GAMMA installation did not patch
    bin/ »). L'Anomaly de base est déjà vérifiée par `anomaly-install`, avant le
    patch — le seul moment où cette vérification est valide.
    """
    corrupted = False
    unverifiable: list[str] = []

    def watch(line: str) -> None:
        # Classifie sur le flux complet, pas sur le tail tronqué de l'erreur :
        # check-md5 réimprime toutes ses erreurs en bloc final, mais un tail de
        # 20 lignes pourrait masquer une vraie corruption noyée au milieu.
        nonlocal corrupted
        stripped = line.strip()
        if any(marker in stripped for marker in markers.CORRUPTION_MARKERS):
            corrupted = True
        elif any(marker in stripped for marker in markers.UNVERIFIABLE_MARKERS):
            unverifiable.append(stripped)
        if on_progress is not None:
            on_progress(line)

    try:
        run(
            "check-md5",
            ["--gamma", str(paths.gamma)],
            on_progress=watch,
            cancel_event=cancel_event,
            download_dir=_gamma_downloads(paths),
        )
    except EngineExecutionError as error:
        if corrupted or not unverifiable:
            raise VerificationError(
                error.subcommand, error.returncode, error.output_tail, error.download_dir
            ) from error
        # Échec uniquement « en ligne » : aucune archive locale en défaut.
    return tuple(dict.fromkeys(unverifiable))
