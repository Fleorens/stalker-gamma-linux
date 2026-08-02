"""Exceptions typées pour la gestion du préfixe Proton partagé."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.i18n import _

# (piège, indice) constatés dans docs/INSTALL-MANUAL.md §6.2 et les guides sources.
_KNOWN_WINETRICKS_HINTS: tuple[tuple[str, str], ...] = (
    (
        "sha256sum mismatch",
        _(
            "The upstream file changed or the download is corrupted. Retry "
            "(winetricks re-downloads); if the error persists, update Proton-GE "
            "(winetricks is bundled with it). SHA warnings on vcrun2022 are "
            "known and safe to ignore as long as the verb succeeds (docs/INSTALL-MANUAL.md §6.2)."
        ),
    ),
    (
        "wineserver not found",
        _(
            "The Proton pointed to by PROTONPATH looks incomplete. Check the "
            "Proton-GE installation (`stalker-gamma-linux prefix-doctor`)."
        ),
    ),
)


def _actionable_hint(output: str) -> str | None:
    for needle, hint in _KNOWN_WINETRICKS_HINTS:
        if needle in output:
            return hint
    return None


class PrefixError(Exception):
    """Erreur de base pour tout ce qui concerne le préfixe Proton."""


class UmuNotFoundError(PrefixError):
    """Le binaire `umu-run` est introuvable dans le PATH."""

    def __init__(self) -> None:
        super().__init__(
            _(
                "umu-run not found in PATH. Install umu-launcher (see "
                "`stalker-gamma-linux doctor` for the command for your distribution). "
                "Manual fallback: protontricks on an existing Steam entry, "
                "documented in docs/INSTALL-MANUAL.md §6.1-6.2."
            )
        )


class UmuDownloadError(PrefixError):
    """Le téléchargement/la pose du zipapp umu-launcher a échoué (`prefix.umu`)."""


class UnsafeArchiveError(PrefixError):
    """Une archive téléchargée contient un membre qui sortirait du répertoire cible."""

    def __init__(self, member: str, reason: str) -> None:
        self.member = member
        self.reason = reason
        super().__init__(
            _(
                "Archive rejected: entry `{member}` is unsafe ({reason}).\n"
                "→ This archive tries to write outside the target directory. "
                "Nothing was extracted. Report the issue if it comes from an "
                "official release."
            ).format(member=member, reason=reason)
        )


class TruncatedDownloadError(PrefixError):
    """Le transfert s'est terminé avant le `Content-Length` annoncé par le serveur."""

    def __init__(self, url: str, expected: int, received: int) -> None:
        self.url = url
        self.expected = expected
        self.received = received
        super().__init__(
            _(
                "Truncated download: {received} bytes received out of the {expected} "
                "announced by the server ({url}).\n"
                "→ Connection cut mid-transfer. Retry; if it keeps happening, "
                "check your connection or a proxy sitting in the way."
            ).format(url=url, expected=expected, received=received)
        )


class ProtonDownloadError(PrefixError):
    """Le téléchargement ou l'extraction de Proton-GE a échoué."""


class ChecksumMismatchError(ProtonDownloadError):
    """L'archive Proton-GE téléchargée ne correspond pas au checksum publié."""

    def __init__(self, release: str, expected: str, actual: str) -> None:
        self.release = release
        self.expected = expected
        self.actual = actual
        super().__init__(
            _(
                "Invalid SHA-512 checksum for {release}: archive rejected and deleted.\n"
                "Expected: {expected}\nGot:      {actual}\n"
                "→ Corrupted or tampered download. Retry; if the error persists, "
                "check your connection and the upstream release on GitHub."
            ).format(release=release, expected=expected, actual=actual)
        )


class PrefixCancelledError(PrefixError):
    """Une opération de préfixe a été annulée via `cancel_event` (GUI)."""

    def __init__(self, what: str) -> None:
        self.what = what
        super().__init__(_("{what} cancelled.").format(what=what))


class PrefixCommandError(PrefixError):
    """Une commande lancée dans le préfixe (via umu-run) a rendu un code non nul."""

    def __init__(self, command: str, returncode: int, log_path: Path, output_tail: str) -> None:
        self.command = command
        self.returncode = returncode
        self.log_path = log_path
        self.output_tail = output_tail
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        return _(
            "Command `{command}` failed (code {code}).\nFull log: {log}\nLast lines:\n{tail}"
        ).format(
            command=self.command, code=self.returncode, log=self.log_path, tail=self.output_tail
        )


class WinetricksVerbError(PrefixCommandError):
    """`winetricks <verb>` a échoué dans le préfixe."""

    def __init__(self, verb: str, returncode: int, log_path: Path, output_tail: str) -> None:
        self.verb = verb
        super().__init__(f"winetricks -q {verb}", returncode, log_path, output_tail)

    def _build_message(self) -> str:
        message = _(
            "Installing the winetricks verb `{verb}` failed (code {code}).\n"
            "Full log: {log}\nLast lines:\n{tail}"
        ).format(verb=self.verb, code=self.returncode, log=self.log_path, tail=self.output_tail)
        hint = _actionable_hint(self.output_tail)
        if hint is not None:
            message += f"\n\n→ {hint}"
        else:
            message += "\n\n→ " + _(
                "Retry `stalker-gamma-linux prefix-doctor --repair`: verbs already "
                "installed are not replayed, only the missing one will be retried."
            )
        return message
