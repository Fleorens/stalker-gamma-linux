"""Exceptions typées pour les erreurs remontées par le moteur gamma-launcher."""

from __future__ import annotations

from stalker_gamma_linux.i18n import _

# (piège, indice) constatés dans docs/INSTALL-MANUAL.md §9 et le code amont.
_KNOWN_HINTS: tuple[tuple[str, str], ...] = (
    (
        "ModDB download link not found",
        _(
            "Dead ModDB mirror upstream (gamma-launcher issue #167). "
            "Update gamma-launcher to the latest release and retry: "
            "the already-downloaded cache is kept."
        ),
    ),
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


def _actionable_hint(output: str) -> str | None:
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

    def __init__(self, subcommand: str, returncode: int, output_tail: str) -> None:
        self.subcommand = subcommand
        self.returncode = returncode
        self.output_tail = output_tail

        message = _(
            "gamma-launcher {subcommand} failed (code {code}).\nLast output lines:\n{tail}"
        ).format(subcommand=subcommand, code=returncode, tail=output_tail)
        hint = _actionable_hint(output_tail)
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
