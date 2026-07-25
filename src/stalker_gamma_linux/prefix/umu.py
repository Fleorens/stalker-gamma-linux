"""Installation automatique d'umu-launcher (zipapp officiel, sans sudo).

umu-launcher est LE prérequis pénible : pas de paquet PyPI (`pipx install`
404), pas de paquet dans les dépôts Fedora/Debian — seul Arch l'empaquette.
L'amont publie en revanche un **zipapp autonome** (~420 Kio, un seul fichier
`umu-run`) dans ses releases GitHub : ce module le télécharge et le dépose
dans `~/.local/bin`, exactement ce que la doc amont demande de faire à la
main. Même pattern que `prefix.download` (Proton-GE) : dernière release via
l'API GitHub avec repli épinglé, téléchargement interruptible, pose atomique.
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
import threading
from pathlib import Path

from stalker_gamma_linux.prefix.download import (
    ProgressCallback,
    download_to,
    read_remote_text,
)
from stalker_gamma_linux.prefix.errors import UmuDownloadError

# Dernière release connue au 2026-07-25 — repli si l'API GitHub est
# injoignable (rate limit) ; les téléchargements directs, eux, passent.
FALLBACK_UMU_RELEASE = "1.4.4"

_RELEASE_BASE_URL = "https://github.com/Open-Wine-Components/umu-launcher/releases/download"
_LATEST_RELEASE_API_URL = (
    "https://api.github.com/repos/Open-Wine-Components/umu-launcher/releases/latest"
)
_UMU_TAG_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")
# Le tar contient exactement `umu/umu-run` (zipapp exécutable) — vérifié sur 1.4.4.
_MEMBER_NAME = "umu/umu-run"


def default_install_dir() -> Path:
    """`~/.local/bin` : sur le PATH par défaut des distributions courantes."""
    return Path.home() / ".local" / "bin"


def resolve_latest_release(*, on_progress: ProgressCallback | None = None) -> str:
    """Tag de la dernière release umu-launcher, via l'API GitHub (repli épinglé)."""
    progress = on_progress or (lambda _line: None)
    try:
        payload = json.loads(read_remote_text(_LATEST_RELEASE_API_URL))
        tag = str(payload.get("tag_name", "")) if isinstance(payload, dict) else ""
    except (OSError, ValueError):
        tag = ""
    if not _UMU_TAG_RE.match(tag):
        progress(f"API GitHub injoignable — repli sur umu-launcher {FALLBACK_UMU_RELEASE}")
        return FALLBACK_UMU_RELEASE
    return tag


def install_umu(
    release: str | None = None,
    install_dir: Path | None = None,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    """Télécharge le zipapp umu-launcher et dépose `umu-run` dans `install_dir`.

    `release` à None = dernière release publiée. Retourne le chemin du
    `umu-run` posé (écrase une version précédente : le zipapp est
    autoporteur, pas d'état à préserver). Lève `UmuDownloadError` en cas de
    problème réseau ou d'archive inattendue. Sans sudo : tout se passe sous
    le home de l'utilisateur.
    """
    progress = on_progress or (lambda _line: None)
    if release is None:
        release = resolve_latest_release(on_progress=on_progress)
    resolved_dir = install_dir if install_dir is not None else default_install_dir()
    target = resolved_dir / "umu-run"

    archive_url = f"{_RELEASE_BASE_URL}/{release}/umu-launcher-{release}-zipapp.tar"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Répertoire temporaire dans resolved_dir : même système de fichiers,
        # le rename final est atomique et un échec ne laisse aucun résidu.
        with tempfile.TemporaryDirectory(dir=resolved_dir) as tmp:
            archive = Path(tmp) / "umu-zipapp.tar"
            progress(f"Téléchargement d'umu-launcher {release}…")
            download_to(archive_url, archive, cancel_event=cancel_event)
            with tarfile.open(archive) as tar:
                tar.extractall(Path(tmp), filter="data")
            extracted = Path(tmp) / _MEMBER_NAME
            if not extracted.is_file() or extracted.stat().st_size == 0:
                raise UmuDownloadError(
                    f"Archive umu-launcher {release} inattendue : "
                    f"`{_MEMBER_NAME}` absent ou vide après extraction"
                )
            extracted.chmod(0o755)
            extracted.replace(target)
    except tarfile.TarError as error:
        raise UmuDownloadError(
            f"Archive umu-launcher {release} corrompue : {error}"
        ) from error
    except OSError as error:
        raise UmuDownloadError(
            f"Téléchargement d'umu-launcher {release} impossible ({archive_url}) : {error}"
        ) from error
    progress(f"umu-run {release} installé dans {resolved_dir}")
    return target


def run_install_umu() -> int:
    """Commande CLI `install-umu` : installe le zipapp et vérifie le PATH."""
    from stalker_gamma_linux import output
    from stalker_gamma_linux.environment import system

    try:
        target = install_umu(on_progress=output.progress)
    except UmuDownloadError as error:
        output.error(str(error))
        return 1

    if system.which("umu-run") is None:
        # Posé au bon endroit mais invisible du PATH de ce shell : le seul cas
        # est un PATH sans ~/.local/bin (rare — Fedora/Debian/Arch l'y mettent).
        output.warn(
            f"umu-run est installé ({target}) mais ~/.local/bin n'est pas dans "
            "ton PATH. Ajoute-le (par ex. `export PATH=\"$HOME/.local/bin:$PATH\"` "
            "dans ~/.bashrc) puis rouvre un terminal."
        )
        return 0
    output.success(f"umu-run opérationnel : {target}")
    return 0
