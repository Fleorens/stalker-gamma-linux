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
    version = updates.local_version_file(tmp_path)
    version.parent.mkdir(parents=True, exist_ok=True)
    version.write_text("920\n")
    return tmp_path


def _patch_remote(monkeypatch: pytest.MonkeyPatch, payloads: dict[str, bytes]) -> list[str]:
    """Sert les charges demandées ; par défaut le numéro de définition est inchangé."""
    urls: list[str] = []
    served = {updates.VERSION_FILE: b"920\n", **payloads}

    def fake(url: str) -> bytes:
        urls.append(url)
        return served[url.rsplit("/", 1)[-1]]

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
        # Numéro de définition + les deux fichiers de définitions.
        assert len(urls) == len(updates.DEFINITION_FILES) + 1


class TestNumeroDeDefinition:
    """Le signal qui fait autorité : le numéro publié par Grokitach."""

    def test_numero_different_signale_une_mise_a_jour(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_remote(monkeypatch, {updates.VERSION_FILE: b"921\n"})

        result = updates.check_for_updates(gamma_dir)

        assert result.is_available
        assert result.local_version == "920"
        assert result.upstream_version == "921"
        assert "920" in result.message and "921" in result.message

    def test_numero_identique_et_definitions_identiques(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_remote(monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n"))

        result = updates.check_for_updates(gamma_dir)

        assert result.status is updates.UpdateStatus.UP_TO_DATE
        assert "920" in result.message

    def test_definition_modifiee_sans_increment_est_detectee(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le filet : Grokitach corrige une liste sans toucher au numéro."""
        payloads = dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n")
        payloads["modpack_maker_list.txt"] = b"directive corrigee\n"
        _patch_remote(monkeypatch, payloads)

        result = updates.check_for_updates(gamma_dir)

        assert result.is_available
        assert result.changed == ("modpack_maker_list.txt",)

    def test_sans_fichier_de_version_on_retombe_sur_les_definitions(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Installations anciennes : pas de numéro local, la comparaison reste possible."""
        updates.local_version_file(gamma_dir).unlink()
        _patch_remote(monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n"))

        result = updates.check_for_updates(gamma_dir)

        assert result.status is updates.UpdateStatus.UP_TO_DATE
        assert result.local_version == ""

    def test_le_numero_ne_passe_pas_par_lapi_github(
        self, gamma_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'API est limitée à 60 req/h : un clic répété ne doit pas la toucher."""
        urls = _patch_remote(
            monkeypatch, dict.fromkeys(updates.DEFINITION_FILES, b"contenu identique\n")
        )

        updates.check_for_updates(gamma_dir)

        assert urls, "aucune requête émise"
        assert all("api.github.com" not in url for url in urls)
        assert all(url.startswith("https://raw.githubusercontent.com/") for url in urls)
