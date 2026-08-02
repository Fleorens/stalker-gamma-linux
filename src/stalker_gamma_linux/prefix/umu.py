"""Installation automatique d'umu-launcher (zipapp officiel, sans sudo).

umu-launcher est LE prérequis pénible : pas de paquet PyPI (`pipx install`
404), pas de paquet dans les dépôts Fedora/Debian — seul Arch l'empaquette.
L'amont publie en revanche un **zipapp autonome** (~420 Kio, un seul fichier
`umu-run`) dans ses releases GitHub : ce module le télécharge et le dépose
dans `~/.local/bin`, exactement ce que la doc amont demande de faire à la
main. Même pattern que `prefix.download` (Proton-GE) : dernière release via
l'API GitHub avec repli épinglé, téléchargement interruptible, pose atomique.

**Intégrité — pourquoi pas de SHA-512 ici alors que Proton-GE en a un.**
L'amont ne publie aucune somme de contrôle : ses releases ne contiennent que
les `.deb`/`.rpm` et le zipapp, sans fichier `.sha512sum` (vérifié sur la
release 1.4.4). Il n'y a donc rien contre quoi comparer, et l'absence de
vérification n'est pas un oubli mais une contrainte amont. Ce qu'on fait à la
place, parce que c'est ce qui casse réellement en pratique :

- `download_to` recoupe la taille reçue avec le `Content-Length` annoncé —
  une connexion coupée en plein transfert ne passe plus pour un succès ;
- `_require_valid_zipapp` exige un `#!` suivi d'une archive ZIP lisible
  contenant `__main__.py`, au lieu du simple « le fichier n'est pas vide ».

Reste la confiance en HTTPS/GitHub pour l'authenticité, comme pour n'importe
quel `curl | sh` d'installation amont. Si l'amont se met à publier des sommes
(ou des attestations d'artefacts), ce module doit les vérifier — même
traitement que Proton-GE.
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
import threading
import zipfile
from pathlib import Path

from stalker_gamma_linux.i18n import _
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


def _require_valid_zipapp(path: Path, release: str) -> str:
    """Vérifie que `path` est un zipapp exécutable, et retourne son point d'entrée.

    Faute de somme de contrôle amont (cf. docstring du module), c'est notre seul
    contrôle d'intégrité de contenu : un zipapp est une archive ZIP précédée
    d'un `#!`, donc un fichier tronqué ou corrompu n'a pas de répertoire central
    ZIP lisible et ne contient pas `__main__.py`. Bien plus solide que
    « le fichier existe et n'est pas vide » — et ça évite de poser dans
    `~/.local/bin` un `umu-run` cassé qui échouerait plus tard, loin d'ici.
    """
    with path.open("rb") as stream:
        shebang = stream.read(2)
    if shebang != b"#!":
        raise UmuDownloadError(
            _(
                "Unexpected umu-launcher archive {release}: `{member}` is not an "
                "executable zipapp (missing shebang)."
            ).format(release=release, member=_MEMBER_NAME)
        )
    try:
        with zipfile.ZipFile(path) as zipapp:
            names = zipapp.namelist()
    except zipfile.BadZipFile as error:
        raise UmuDownloadError(
            _(
                "Corrupted umu-launcher zipapp {release}: unreadable ZIP directory "
                "({error}). The download is probably incomplete — retry."
            ).format(release=release, error=error)
        ) from error
    if "__main__.py" not in names:
        raise UmuDownloadError(
            _("Unexpected umu-launcher zipapp {release}: no `__main__.py` entry point.").format(
                release=release
            )
        )
    return _MEMBER_NAME


def resolve_latest_release(*, on_progress: ProgressCallback | None = None) -> str:
    """Tag de la dernière release umu-launcher, via l'API GitHub (repli épinglé)."""
    progress = on_progress or (lambda _line: None)
    try:
        payload = json.loads(read_remote_text(_LATEST_RELEASE_API_URL))
        tag = str(payload.get("tag_name", "")) if isinstance(payload, dict) else ""
    except (OSError, ValueError):
        tag = ""
    if not _UMU_TAG_RE.match(tag):
        progress(
            _("GitHub API unreachable — falling back to umu-launcher {release}").format(
                release=FALLBACK_UMU_RELEASE
            )
        )
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
            progress(_("Downloading umu-launcher {release}…").format(release=release))
            download_to(archive_url, archive, cancel_event=cancel_event)
            with tarfile.open(archive) as tar:
                tar.extractall(Path(tmp), filter="data")
            extracted = Path(tmp) / _MEMBER_NAME
            if not extracted.is_file() or extracted.stat().st_size == 0:
                raise UmuDownloadError(
                    _(
                        "Unexpected umu-launcher archive {release}: "
                        "`{member}` missing or empty after extraction"
                    ).format(release=release, member=_MEMBER_NAME)
                )
            _require_valid_zipapp(extracted, release)
            extracted.chmod(0o755)
            extracted.replace(target)
    except tarfile.TarError as error:
        raise UmuDownloadError(
            _("Corrupted umu-launcher archive {release}: {error}").format(
                release=release, error=error
            )
        ) from error
    except OSError as error:
        raise UmuDownloadError(
            _("Could not download umu-launcher {release} ({url}): {error}").format(
                release=release, url=archive_url, error=error
            )
        ) from error
    progress(_("umu-run {release} installed in {dir}").format(release=release, dir=resolved_dir))
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
            _(
                "umu-run is installed ({target}) but ~/.local/bin is not in "
                'your PATH. Add it (e.g. `export PATH="$HOME/.local/bin:$PATH"` '
                "in ~/.bashrc) then open a new terminal."
            ).format(target=target)
        )
        return 0
    output.success(_("umu-run ready: {target}").format(target=target))
    return 0
