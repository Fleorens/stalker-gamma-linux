"""Téléchargement vérifié (SHA-512) d'une release Proton-GE depuis GitHub."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from stalker_gamma_linux.prefix.errors import ChecksumMismatchError, ProtonDownloadError

ProgressCallback = Callable[[str], None]

# Décision utilisateur (2026-07-19) : on installe la *dernière* release GE,
# résolue via l'API GitHub. Ce repli épinglé (dernière release connue au
# 2026-07-19) ne sert que si l'API est injoignable — typiquement rate limit,
# qui ne touche pas les téléchargements directs.
FALLBACK_GE_RELEASE = "GE-Proton11-1"

_RELEASE_BASE_URL = "https://github.com/GloriousEggroll/proton-ge-custom/releases/download"
_LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
)
_GE_TAG_RE = re.compile(r"^GE-Proton\d+-\d+$")
_FETCH_TIMEOUT_SECONDS = 30
_HASH_CHUNK_BYTES = 1024 * 1024
_SHA512_HEX_LENGTH = 128


def _default_install_dir() -> Path:
    """`compatibilitytools.d` du Steam par défaut — c'est aussi là qu'umu installe les siens."""
    return Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d"


def _read_remote_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        return str(response.read().decode("utf-8"))


def _download_to(url: str, dest: Path) -> None:
    with (
        urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT_SECONDS) as response,
        dest.open("wb") as output,
    ):
        shutil.copyfileobj(response, output)


def _sha512(path: Path) -> str:
    digest = hashlib.sha512()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_checksum(release: str) -> str:
    url = f"{_RELEASE_BASE_URL}/{release}/{release}.sha512sum"
    tokens = _read_remote_text(url).split()
    if not tokens or len(tokens[0]) != _SHA512_HEX_LENGTH:
        raise ProtonDownloadError(f"Fichier de checksum illisible pour {release} ({url})")
    return tokens[0]


def resolve_latest_ge_release(*, on_progress: ProgressCallback | None = None) -> str:
    """Tag de la dernière release GE-Proton publiée, via l'API GitHub.

    Repli sur `FALLBACK_GE_RELEASE` si l'API est injoignable ou renvoie un tag
    inattendu : l'API est rate-limitée (60 req/h sans authentification), pas
    les téléchargements de release.
    """
    progress = on_progress or (lambda _line: None)
    try:
        payload = json.loads(_read_remote_text(_LATEST_RELEASE_API_URL))
        tag = str(payload.get("tag_name", "")) if isinstance(payload, dict) else ""
    except (OSError, ValueError):
        tag = ""
    if not _GE_TAG_RE.match(tag):
        progress(f"API GitHub injoignable — repli sur {FALLBACK_GE_RELEASE}")
        return FALLBACK_GE_RELEASE
    return tag


def download_proton_ge(
    release: str | None = None,
    install_dir: Path | None = None,
    *,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Télécharge et installe une release GE dans `install_dir`, SHA-512 vérifié.

    `release` à None (défaut) = dernière release publiée (décision utilisateur),
    résolue via `resolve_latest_ge_release`. Idempotent : si la release est déjà
    présente et complète, ne télécharge rien. Retourne le répertoire du build
    installé. Lève `ChecksumMismatchError` si l'archive ne correspond pas au
    checksum publié, `ProtonDownloadError` pour toute autre erreur réseau/archive.
    """
    progress = on_progress or (lambda _line: None)
    if release is None:
        release = resolve_latest_ge_release(on_progress=on_progress)
    resolved_dir = install_dir if install_dir is not None else _default_install_dir()
    target = resolved_dir / release
    if (target / "proton").exists():
        return target

    resolved_dir.mkdir(parents=True, exist_ok=True)
    archive_url = f"{_RELEASE_BASE_URL}/{release}/{release}.tar.gz"
    try:
        expected = _remote_checksum(release)
        # Répertoire temporaire dans resolved_dir : même système de fichiers,
        # le rename final est atomique et un échec ne laisse aucun résidu.
        with tempfile.TemporaryDirectory(dir=resolved_dir) as tmp:
            archive = Path(tmp) / f"{release}.tar.gz"
            progress(f"Téléchargement de {release}…")
            _download_to(archive_url, archive)
            progress("Vérification du checksum SHA-512…")
            actual = _sha512(archive)
            if actual != expected:
                raise ChecksumMismatchError(release, expected, actual)
            progress("Extraction…")
            with tarfile.open(archive) as tar:
                tar.extractall(Path(tmp), filter="data")
            extracted = Path(tmp) / release
            if not (extracted / "proton").exists():
                raise ProtonDownloadError(
                    f"Archive {release} inattendue : exécutable `proton` absent après extraction"
                )
            if target.exists():
                # Reste d'une extraction interrompue (le cas complet a retourné plus haut).
                shutil.rmtree(target)
            extracted.rename(target)
    except tarfile.TarError as error:
        raise ProtonDownloadError(f"Archive {release} corrompue : {error}") from error
    except OSError as error:
        raise ProtonDownloadError(
            f"Téléchargement de {release} impossible ({archive_url}) : {error}"
        ) from error
    progress(f"{release} installé dans {resolved_dir}")
    return target
