"""Exceptions typées pour les erreurs remontées par le moteur gamma-launcher."""

from __future__ import annotations

import re
from pathlib import Path

from stalker_gamma_linux.engine import markers
from stalker_gamma_linux.i18n import _

# Signature réelle du refus ModDB, telle qu'elle apparaît dans la sortie :
# `launcher.exceptions.ModDBDownloadError: Download link not found when
# requesting https://www.moddb.com/…` (gamma-launcher ne rattrape pas
# l'exception, on reçoit donc la traceback).
_MODDB_URL_RE = re.compile(r"https?://(?:www\.)?moddb\.com/\S+")

_RETRY_FAILED_HINT = _(
    "run `stalker-gamma-linux install --retry-failed` (or the same command "
    "again): files already there and matching their MD5 are not downloaded a "
    "second time."
)


def _moddb_hint(
    output: str,
    download_dir: Path | None,
    *,
    mod_name: str | None = None,
    archive_name: str | None = None,
    expected_md5: str | None = None,
) -> str:
    """Procédure de rattrapage manuel d'un fichier que ModDB refuse de servir.

    Miroir mort, mod déplacé/retiré en amont, ou défi Cloudflare/403 : de
    l'extérieur c'est indiscernable (`engine.markers`), et dans tous les cas
    relancer tel quel ne change rien. Mais gamma-launcher télécharge avec
    `use_cached=True` et un nom d'archive déterministe : un fichier déposé à la
    main au bon endroit, sous le bon nom, est repris tel quel à la relance.
    D'où cette procédure plutôt qu'un échec sec — c'est le mur classique d'une
    installation GAMMA, et il n'a rien de définitif.
    """
    match = _MODDB_URL_RE.search(output)
    page = match.group(0) if match else _("the ModDB page shown above")
    destination = (
        str(download_dir) if download_dir is not None else _("the downloads folder of your install")
    )
    context = ""
    if mod_name:
        context += _("Mod: {name}\n").format(name=mod_name)
    if archive_name:
        context += _("Expected file: {name}\n").format(name=archive_name)
    if expected_md5:
        context += _("Expected MD5: {md5}\n").format(md5=expected_md5)
    return _(
        "ModDB refused this download — dead mirror, mod moved/removed upstream, "
        "or Cloudflare challenge (indistinguishable from here). Nothing already "
        "downloaded is lost. Fetch this one file yourself:\n"
        "{context}"
        "   1. open {page} in your browser and download the file;\n"
        "   2. drop it in {destination}, under the exact name shown above (or "
        "gamma-launcher won't recognize it) — check its MD5 against the page "
        "if it gives one;\n"
        "   3. {retry_hint}\n"
        "   If it happens on several mods in a row, ModDB itself may be "
        "throttling you — wait a few minutes before the next one.\n"
        "   gamma-launcher does not skip a broken mod and continue on its own "
        "(only `check-md5` does); if this keeps happening, consider opening an "
        "issue at https://github.com/Mord3rca/gamma-launcher/issues with the "
        "mod name above."
    ).format(context=context, page=page, destination=destination, retry_hint=_RETRY_FAILED_HINT)


def _corruption_hint(
    output: str,
    download_dir: Path | None,
    *,
    mod_name: str | None = None,
    archive_name: str | None = None,
    expected_md5: str | None = None,
) -> str:
    """L'archive en cache ne correspond pas à son hash — rien à faire, juste relancer.

    Seule des trois causes qui ne demande rien à l'utilisateur : le retrait de
    l'archive abîmée est le mécanisme de `verify --repair`/`integrity.repair`
    (T12), réutilisé tel quel par `install --retry-failed`.
    """
    del expected_md5  # une corruption locale se soigne sans dépôt manuel
    context = _("Mod: {name}\n").format(name=mod_name) if mod_name else ""
    file_line = _("File: {name}\n").format(name=archive_name) if archive_name else ""
    destination = str(download_dir) if download_dir is not None else _("the downloads folder")
    return _(
        "The cached archive does not match its expected hash — a corrupted or "
        "truncated download, not a ModDB issue.\n"
        "{context}{file_line}"
        "Nothing to fetch yourself: run `stalker-gamma-linux install "
        "--retry-failed` — it removes the bad archive from {destination} and "
        "lets the engine redownload it."
    ).format(context=context, file_line=file_line, destination=destination)


def _network_unreachable_hint(
    output: str,
    download_dir: Path | None,
    *,
    mod_name: str | None = None,
    archive_name: str | None = None,
    expected_md5: str | None = None,
) -> str:
    """Le réseau (ou ModDB dans son ensemble) ne répond pas — pas un mod précis.

    `requests.exceptions.ConnectionError` n'est levée qu'après trois tentatives
    internes de gamma-launcher (`tenacity`, 30 s d'intervalle) : ce n'est ni
    une archive locale en tort, ni une page ModDB qui a changé — attendre est
    le seul remède sensé.
    """
    del output, download_dir, archive_name, expected_md5  # rien de spécifique à un mod ici
    context = _(" (was installing {name})").format(name=mod_name) if mod_name else ""
    return _(
        "ModDB — or your network — did not answer{context}, even after "
        "gamma-launcher's own retries. This isn't specific to one mod: wait a "
        "few minutes and run the same command again, it resumes where it "
        "stopped (nothing already downloaded is re-fetched)."
    ).format(context=context)


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

_HINT_BY_CAUSE = {
    markers.FailureCause.LOCAL_CORRUPTION: _corruption_hint,
    markers.FailureCause.MOD_LINK_BROKEN: _moddb_hint,
    markers.FailureCause.NETWORK_UNREACHABLE: _network_unreachable_hint,
}


def _actionable_hint(
    output: str,
    download_dir: Path | None = None,
    *,
    mod_name: str | None = None,
    archive_name: str | None = None,
    expected_md5: str | None = None,
) -> str | None:
    cause = markers.classify(output)
    if cause is not None:
        return _HINT_BY_CAUSE[cause](
            output,
            download_dir,
            mod_name=mod_name,
            archive_name=archive_name,
            expected_md5=expected_md5,
        )
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
    """`gamma-launcher <sous-commande>` a rendu un code de retour non nul.

    `mod_name`/`archive_name`/`expected_md5` (optionnels) identifient le mod en
    cours de traitement au moment de l'échec — voir `engine.runner._install`,
    seul appelant qui les renseigne : ils viennent du flux de progression
    complet, pas de `output_tail` (les 20 dernières lignes), qui peut ne plus
    contenir la ligne « Processing mod » sur une trace longue (`AttributeError`
    sur `unpackinfo`, issues amont #283/#284). `cause`, lui, se lit fiablement
    dans `output_tail` : la ligne qui déclenche l'erreur est toujours la
    dernière.
    """

    def __init__(
        self,
        subcommand: str,
        returncode: int,
        output_tail: str,
        download_dir: Path | None = None,
        *,
        mod_name: str | None = None,
        archive_name: str | None = None,
        expected_md5: str | None = None,
    ) -> None:
        self.subcommand = subcommand
        self.returncode = returncode
        self.output_tail = output_tail
        # Dossier où la sous-commande dépose ses archives : il diffère d'une
        # sous-commande à l'autre (cache pour `anomaly-install`,
        # `<gamma>/downloads` pour `full-install`), et un remède qui désigne le
        # mauvais dossier fait perdre un téléchargement manuel à l'utilisateur.
        self.download_dir = download_dir
        self.mod_name = mod_name
        self.archive_name = archive_name
        self.expected_md5 = expected_md5
        self.cause = markers.classify(output_tail)

        message = _(
            "gamma-launcher {subcommand} failed (code {code}).\nLast output lines:\n{tail}"
        ).format(subcommand=subcommand, code=returncode, tail=output_tail)
        hint = _actionable_hint(
            output_tail,
            download_dir,
            mod_name=mod_name,
            archive_name=archive_name,
            expected_md5=expected_md5,
        )
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


class DepositMismatchError(EngineError):
    """Un fichier déposé à la main sous `<gamma>/downloads` n'a pas le MD5 attendu.

    Levée par `orchestrator.run_retry_failed` avant même de relancer le
    moteur : sans ce garde-fou, `full-install` re-résout la page ModDB, voit le
    hash ne pas correspondre et retélécharge le fichier en silence — sans
    jamais dire à l'utilisateur que ce qu'il a déposé n'était pas le bon.
    """

    def __init__(self, mod_name: str, path: Path, expected_md5: str, actual_md5: str) -> None:
        self.mod_name = mod_name
        self.path = path
        self.expected_md5 = expected_md5
        self.actual_md5 = actual_md5
        super().__init__(
            _(
                "The file dropped at {path} (for « {mod} ») does not have the "
                "expected MD5.\n"
                "  expected: {expected}\n"
                "  actual:   {actual}\n"
                "→ Check you downloaded the right file from the ModDB page (not "
                "an ad or a wrong mirror), then run `install --retry-failed` again."
            ).format(path=path, mod=mod_name, expected=expected_md5, actual=actual_md5)
        )
