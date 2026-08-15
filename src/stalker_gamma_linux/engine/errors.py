"""Exceptions typées pour les erreurs remontées par le moteur gamma-launcher."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from stalker_gamma_linux.i18n import _

# Signature réelle du refus ModDB, telle qu'elle apparaît dans la sortie :
# `launcher.exceptions.ModDBDownloadError: Download link not found when
# requesting https://www.moddb.com/…` (gamma-launcher ne rattrape pas
# l'exception, on reçoit donc la traceback). L'ancien indice cherchait
# « ModDB download link not found », chaîne qui n'existe nulle part en amont :
# il ne s'est jamais déclenché, et le mur ModDB tombait dans le conseil
# générique « réessaie » — précisément ce qui ne marche pas ici.
_MODDB_MARKERS = ("Download link not found when requesting", "ModDBDownloadError")
_MODDB_URL_RE = re.compile(r"https?://(?:www\.)?moddb\.com/\S+")


def _moddb_hint(output: str, download_dir: Path | None) -> str:
    """Procédure de rattrapage manuel d'un fichier que ModDB refuse de servir.

    Miroir mort ou défi Cloudflare : de l'extérieur c'est indiscernable, et dans
    les deux cas relancer ne change rien. Mais gamma-launcher télécharge avec
    `use_cached=True` et un nom d'archive déterministe : un fichier déposé à la
    main au bon endroit est repris tel quel à la relance. D'où cette procédure
    en trois lignes plutôt qu'un échec sec — c'est le mur classique d'une
    installation GAMMA, et il n'a rien de définitif.
    """
    match = _MODDB_URL_RE.search(output)
    page = match.group(0) if match else _("the ModDB page shown above")
    destination = (
        str(download_dir) if download_dir is not None else _("the downloads folder of your install")
    )
    return _(
        "ModDB refused this download — dead mirror or Cloudflare challenge "
        "(indistinguishable from here). Nothing already downloaded is lost, and "
        "retrying as-is won't help. Fetch this one file yourself:\n"
        "   1. open {page} in your browser and download the file;\n"
        "   2. drop it in {destination};\n"
        "   3. run the same command again — files already there are not "
        "downloaded a second time.\n"
        "   If it happens on many mods in a row, update gamma-launcher first: "
        "dead mirrors get fixed upstream."
    ).format(page=page, destination=destination)


# (piège, indice) constatés dans docs/INSTALL-MANUAL.md §9 et le code amont.
_KNOWN_HINTS: tuple[tuple[str, str], ...] = (
    (
        "symbol lookup",
        _(
            "Known issue with the release binary on some distributions. "
            "Retry with `LD_PRELOAD=/usr/lib/libreadline.so`, or install "
            "gamma-launcher via pip in a venv instead of the standalone binary."
        ),
    ),
    (
        "Couldn't find path to unrar library",
        _(
            "libunrar is missing. Install it (see `stalker-gamma-linux doctor` "
            "for the command for your distribution) and retry."
        ),
    ),
)


HintBuilder = Callable[[str, Path | None], str]

# Indices qui ont besoin du contexte (URL dans la sortie, dossier de dépôt).
_CONTEXTUAL_HINTS: tuple[tuple[tuple[str, ...], HintBuilder], ...] = (
    (_MODDB_MARKERS, _moddb_hint),
)


def _actionable_hint(output: str, download_dir: Path | None = None) -> str | None:
    for markers, build in _CONTEXTUAL_HINTS:
        if any(marker in output for marker in markers):
            return build(output, download_dir)
    for needle, hint in _KNOWN_HINTS:
        if needle in output:
            return hint
    return None


class EngineError(Exception):
    """Erreur de base pour tout ce qui concerne le moteur gamma-launcher."""


class EngineNotFoundError(EngineError):
    """Le binaire `gamma-launcher` est introuvable dans le PATH."""

    def __init__(self) -> None:
        super().__init__(
            _(
                "gamma-launcher not found in PATH. Install it in the same "
                "environment as stalker-gamma-linux, for example: "
                "pip install 'gamma-launcher @ "
                "git+https://github.com/Mord3rca/gamma-launcher.git@v3.1'"
            )
        )


class EngineCancelledError(EngineError):
    """`gamma-launcher <sous-commande>` a été interrompu via `cancel_event` (GUI)."""

    def __init__(self, subcommand: str) -> None:
        self.subcommand = subcommand
        super().__init__(_("gamma-launcher {subcommand} cancelled.").format(subcommand=subcommand))


class EngineExecutionError(EngineError):
    """`gamma-launcher <sous-commande>` a rendu un code de retour non nul."""

    def __init__(
        self,
        subcommand: str,
        returncode: int,
        output_tail: str,
        download_dir: Path | None = None,
    ) -> None:
        self.subcommand = subcommand
        self.returncode = returncode
        self.output_tail = output_tail
        # Dossier où la sous-commande dépose ses archives : il diffère d'une
        # sous-commande à l'autre (cache pour `anomaly-install`,
        # `<gamma>/downloads` pour `full-install`), et un remède qui désigne le
        # mauvais dossier fait perdre un téléchargement manuel à l'utilisateur.
        self.download_dir = download_dir

        message = _(
            "gamma-launcher {subcommand} failed (code {code}).\nLast output lines:\n{tail}"
        ).format(subcommand=subcommand, code=returncode, tail=output_tail)
        hint = _actionable_hint(output_tail, download_dir)
        if hint is not None:
            message += f"\n\n→ {hint}"
        else:
            message += "\n\n→ " + _(
                "Retry the same command: the cache already downloaded and "
                "verified is not re-downloaded."
            )
        super().__init__(message)


class VerificationError(EngineExecutionError):
    """`check-anomaly` ou `check-md5` a détecté des fichiers invalides/manquants."""
