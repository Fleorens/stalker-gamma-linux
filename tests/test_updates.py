"""Vérification de mise à jour (`updates`) — en lecture seule, c'est tout l'enjeu.

L'entrée de menu « Check for updates » lançait un `full-install` complet, qui
réécrit la liste de mods MO2 du joueur. Ces tests verrouillent le contrat : la
vérification compare, et n'écrit rien.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux import updates


@pytest.fixture
def gamma_dir(tmp_path: Path) -> Path:
    definitions = updates.local_definition_dir(tmp_path)
    definitions.mkdir(parents=True)
    for filename in updates.DEFINITION_FILES:
        (definitions / filename).write_bytes(b"contenu identique\n")
    return tmp_path


def _patch_remote(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, bytes]) -> list[str]:
    urls: list[str] = []

    def fake(url: str) -> bytes:
        urls.append(url)
        return payloads[url.rsplit("/", 1)[-1]]

    monkeypatch.setattr(updates, "read_remote_bytes", fake)
    return urls


class TestCheckForUpdates:
    def test_a_jour(self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_remote(monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n"))

        result = updates.check_for_updates(gamma_dir)

        assert result.status is updates.UpdateStatus.UP_TO_DATE
        assert not result.is_available

    def test_mise_a_jour_disponible(self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payloads = dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n")
        payloads["modlist.txt"] = b"un nouveau mod est arrive\n"
        _patch_remote(monkeypatch, payloads)

        result = updates.check_for_updates(gamma_dir)

        assert result.is_available
        assert result.changed == ("modlist.txt",)

    def test_les_fins_de_ligne_ne_comptent_pas(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le dépôt est en LF, la copie locale peut être en CRLF : pas une mise à jour."""
        for filename in updates.DEFINITION_FILES:
            (updates.local_definition_dir(gamma_dir) / filename).write_bytes(
                b"contenu identique\r\n"
            )
        _patch_remote(monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n"))

        assert updates.check_for_updates(gamma_dir).status is updates.UpdateStatus.UP_TO_DATE

    def test_reseau_coupe_ne_pretend_pas_a_jour(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ne jamais annoncer « à jour » sur une simple absence de réponse."""

        def boom(url: str) -> bytes:
            raise OSError("réseau injoignable")

        monkeypatch.setattr(updates, "read_remote_bytes", boom)

        result = updates.check_for_updates(gamma_dir)

        assert result.status is updates.UpdateStatus.UNKNOWN
        assert not result.is_available

    def test_sans_definition_locale(self, tmp_path: Path) -> None:
        result = updates.check_for_updates(tmp_path)

        assert result.status is updates.UpdateStatus.UNKNOWN

    def test_nécrit_rien_sur_le_disque(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le contrat central : vérifier ne modifie pas l'installation."""
        payloads = dict.fromkeys(updates.DEFINITION_FILES, b"tout a change\n")
        _patch_remote(monkeypatch, payloads)
        before = {
            path: path.read_bytes() for path in sorted(gamma_dir.rglob("*")) if path.is_file()
        }

        updates.check_for_updates(gamma_dir)

        after = {path: path.read_bytes() for path in sorted(gamma_dir.rglob("*")) if path.is_file()}
        assert after == before

    def test_interroge_le_bon_depot(self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        urls = _patch_remote(
            monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n")
        )

        updates.check_for_updates(gamma_dir)

        assert all(updates.UPSTREAM_REPO in url for url in urls)
        assert len(urls) == len(updates.DEFINITION_FILES)
