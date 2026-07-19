"""Exceptions typées pour la gestion du préfixe Proton partagé."""

from __future__ import annotations

from pathlib import Path

# (piège, indice) constatés dans docs/INSTALL-MANUAL.md §6.2 et les guides sources.
_KNOWN_WINETRICKS_HINTS: tuple[tuple[str, str], ...] = (
    (
        "sha256sum mismatch",
        "Le fichier amont a changé ou le téléchargement est corrompu. Relance "
        "(winetricks retélécharge) ; si l'erreur persiste, mets à jour Proton-GE "
        "(winetricks y est embarqué). Les avertissements SHA sur vcrun2022 sont "
        "connus et ignorables tant que le verb réussit (docs/INSTALL-MANUAL.md §6.2).",
    ),
    (
        "wineserver not found",
        "Le Proton pointé par PROTONPATH semble incomplet. Vérifie l'installation "
        "de Proton-GE (`stalker-gamma-linux prefix-doctor`).",
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
            "umu-run introuvable dans le PATH. Installe umu-launcher (voir "
            "`stalker-gamma-linux doctor` pour la commande adaptée à ta distribution). "
            "Voie de secours manuelle : protontricks sur une entrée Steam existante, "
            "documentée dans docs/INSTALL-MANUAL.md §6.1-6.2."
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
            f"Checksum SHA-512 invalide pour {release} : archive rejetée et supprimée.\n"
            f"Attendu : {expected}\nObtenu  : {actual}\n"
            "→ Téléchargement corrompu ou compromis. Relance ; si l'erreur persiste, "
            "vérifie ta connexion et la release amont sur GitHub."
        )


class PrefixCommandError(PrefixError):
    """Une commande lancée dans le préfixe (via umu-run) a rendu un code non nul."""

    def __init__(self, command: str, returncode: int, log_path: Path, output_tail: str) -> None:
        self.command = command
        self.returncode = returncode
        self.log_path = log_path
        self.output_tail = output_tail
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        return (
            f"La commande `{self.command}` a échoué (code {self.returncode}).\n"
            f"Journal complet : {self.log_path}\n"
            f"Dernières lignes :\n{self.output_tail}"
        )


class WinetricksVerbError(PrefixCommandError):
    """`winetricks <verb>` a échoué dans le préfixe."""

    def __init__(self, verb: str, returncode: int, log_path: Path, output_tail: str) -> None:
        self.verb = verb
        super().__init__(f"winetricks -q {verb}", returncode, log_path, output_tail)

    def _build_message(self) -> str:
        message = (
            f"L'installation du verb winetricks `{self.verb}` a échoué "
            f"(code {self.returncode}).\n"
            f"Journal complet : {self.log_path}\n"
            f"Dernières lignes :\n{self.output_tail}"
        )
        hint = _actionable_hint(self.output_tail)
        if hint is not None:
            message += f"\n\n→ {hint}"
        else:
            message += (
                "\n\n→ Relance `stalker-gamma-linux prefix-doctor --repair` : les verbs "
                "déjà installés ne sont pas rejoués, seul le manquant sera retenté."
            )
        return message
