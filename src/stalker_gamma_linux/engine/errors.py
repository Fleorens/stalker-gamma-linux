"""Exceptions typées pour les erreurs remontées par le moteur gamma-launcher."""

from __future__ import annotations

# (piège, indice) constatés dans docs/INSTALL-MANUAL.md §9 et le code amont.
_KNOWN_HINTS: tuple[tuple[str, str], ...] = (
    (
        "ModDB download link not found",
        "Miroir ModDB mort côté amont (issue #167 de gamma-launcher). "
        "Mets à jour gamma-launcher vers la dernière release puis relance : "
        "le cache déjà téléchargé est conservé.",
    ),
    (
        "symbol lookup",
        "Erreur connue avec le binaire de release sur certaines distributions. "
        "Relance avec `LD_PRELOAD=/usr/lib/libreadline.so`, ou installe "
        "gamma-launcher via pip dans un venv plutôt que le binaire autonome.",
    ),
    (
        "Couldn't find path to unrar library",
        "libunrar est absente. Installe-la (voir `stalker-gamma-linux doctor` "
        "pour la commande adaptée à ta distribution) puis relance.",
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
            "gamma-launcher introuvable dans le PATH. Installe-le dans le même "
            "environnement que stalker-gamma-linux, par exemple : "
            "pip install 'gamma-launcher @ "
            "git+https://github.com/Mord3rca/gamma-launcher.git@v3.1'"
        )


class EngineExecutionError(EngineError):
    """`gamma-launcher <sous-commande>` a rendu un code de retour non nul."""

    def __init__(self, subcommand: str, returncode: int, output_tail: str) -> None:
        self.subcommand = subcommand
        self.returncode = returncode
        self.output_tail = output_tail

        message = (
            f"gamma-launcher {subcommand} a échoué (code {returncode}).\n"
            f"Dernières lignes de sortie :\n{output_tail}"
        )
        hint = _actionable_hint(output_tail)
        if hint is not None:
            message += f"\n\n→ {hint}"
        else:
            message += (
                "\n\n→ Relance la même commande : le cache déjà téléchargé et "
                "vérifié n'est pas retéléchargé."
            )
        super().__init__(message)


class VerificationError(EngineExecutionError):
    """`check-anomaly` ou `check-md5` a détecté des fichiers invalides/manquants."""
