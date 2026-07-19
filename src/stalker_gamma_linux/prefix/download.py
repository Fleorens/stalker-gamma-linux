"""Téléchargement vérifié (SHA-512) d'une release Proton-GE depuis GitHub."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from stalker_gamma_linux.prefix.errors import ChecksumMismatchError, ProtonDownloadError

ProgressCallback = Callable[[str], None]

# Dernière release de la lignée GE-Proton10 au 2026-07-19. On reste sur la
# lignée 10, alignée avec la recommandation « Proton 9/10 » du manuel — la
# lignée 11 et la matrice de compatibilité MO2/GE sont ⚠ À VALIDER en T05.
RECOMMENDED_GE_RELEASE = "GE-Proton10-34"

_RELEASE_BASE_URL = "https://github.com/GloriousEggroll/proton-ge-custom/releases/download"
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


def download_proton_ge(
    release: str = RECOMMENDED_GE_RELEASE,
    install_dir: Path | None = None,
    *,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Télécharge et installe `release` dans `install_dir`, checksum SHA-512 vérifié.

    Idempotent : si la release est déjà présente et complète, ne télécharge rien.
    Retourne le répertoire du build installé. Lève `ChecksumMismatchError` si
    l'archive ne correspond pas au checksum publié, `ProtonDownloadError` pour
    toute autre erreur réseau/archive.
    """
    progress = on_progress or (lambda _line: None)
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
