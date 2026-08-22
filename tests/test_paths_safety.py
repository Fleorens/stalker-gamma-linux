"""Garde-fous de chemin (`paths_safety`) — voir tasks/T11-securite-suppression-chemins.md.

Chaque test couvre exactement un des refus listés dans le prompt de T11, plus
le cas nominal. Tout est logique pure : `home` pose un `Path.home()` sous
`tmp_path`, mais la validation elle-même ne fait que `resolve`/`is_symlink`/
`is_dir`, jamais d'écriture ni de lecture de contenu.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from stalker_gamma_linux import paths_safety


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home" / "user"
    home_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home_dir))
    return home_dir


def _install(home: Path, *, marker: str = "anomaly") -> Path:
    """Une install GAMMA plausible : `<target>/<marker>/`."""
    target = home / "Games" / "stalker-gamma"
    (target / marker).mkdir(parents=True)
    return target


class TestResolveWipeTarget:
    def test_cible_inexistante_retourne_none(self, tmp_path: Path) -> None:
        assert paths_safety.resolve_wipe_target(tmp_path / "does-not-exist") is None

    def test_cible_existante_est_resolue(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        target.mkdir()

        assert paths_safety.resolve_wipe_target(target) == target.resolve()


class TestIsSafeWipeTarget:
    def test_cas_nominal(self, home: Path) -> None:
        target = _install(home)

        assert paths_safety.is_safe_wipe_target(target, target.resolve())

    @pytest.mark.parametrize(
        "root",
        [
            "/",
            "/home",
            "/root",
            "/usr",
            "/etc",
            "/var",
            "/opt",
            "/boot",
            "/bin",
            "/sbin",
            "/lib",
            "/lib64",
            "/srv",
            "/mnt",
            "/media",
            "/tmp",
        ],
    )
    def test_racines_systeme_refusees(self, root: str) -> None:
        path = Path(root)

        assert not paths_safety.is_safe_wipe_target(path, path)

    def test_home_refuse(self, home: Path) -> None:
        assert not paths_safety.is_safe_wipe_target(home, home)

    def test_parent_de_home_refuse(self, home: Path) -> None:
        assert not paths_safety.is_safe_wipe_target(home.parent, home.parent)

    def test_sibling_de_home_refuse(self, home: Path) -> None:
        sibling = home.parent / "quelqu-un-d-autre"
        sibling.mkdir()

        assert not paths_safety.is_safe_wipe_target(sibling, sibling)

    def test_symlink_vers_une_install_legitime_refuse(self, home: Path, tmp_path: Path) -> None:
        real_install = _install(home)
        link = tmp_path / "lien"
        link.symlink_to(real_install)

        assert not paths_safety.is_safe_wipe_target(link, link.resolve())

    def test_chemin_relatif_refuse(self, home: Path) -> None:
        target = _install(home)
        relative = Path("Games") / "stalker-gamma"

        assert not paths_safety.is_safe_wipe_target(relative, target.resolve())

    def test_chemin_avec_dotdot_refuse(self, home: Path) -> None:
        target = _install(home)
        raw = home / "Games" / "other" / ".." / "stalker-gamma"

        assert not paths_safety.is_safe_wipe_target(raw, target.resolve())

    def test_cible_inexistante_refusee(self, home: Path) -> None:
        missing = home / "Games" / "stalker-gamma"

        assert not paths_safety.is_safe_wipe_target(missing, missing)

    def test_dossier_existant_sans_marqueur_refuse(self, home: Path) -> None:
        target = home / "Games" / "stalker-gamma"
        (target / "random-stuff").mkdir(parents=True)

        assert not paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_marqueur_gamma_accepte(self, home: Path) -> None:
        target = _install(home, marker="gamma")

        assert paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_marqueur_mods_accepte(self, home: Path) -> None:
        target = _install(home, marker="mods")

        assert paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_marqueur_prefix_accepte(self, home: Path) -> None:
        target = _install(home, marker="prefix")

        assert paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_marqueur_fichier_etat_install_accepte(self, home: Path) -> None:
        target = home / "Games" / "stalker-gamma"
        target.mkdir(parents=True)
        (target / "install-state.toml").write_text("[installs]\n")

        assert paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_repertoire_courant_refuse(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = _install(home)
        monkeypatch.chdir(target)

        assert not paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_venv_courant_refuse(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = _install(home)
        monkeypatch.setattr(sys, "prefix", str(target))

        assert not paths_safety.is_safe_wipe_target(target, target.resolve())

    def test_trop_peu_profond_refuse(self) -> None:
        shallow = Path("/x")

        assert not paths_safety.is_safe_wipe_target(shallow, shallow)


class TestValidateWipeTarget:
    def test_cible_dangereuse_leve_avec_chemin_et_raison(self, home: Path) -> None:
        with pytest.raises(paths_safety.UnsafeWipeTargetError) as excinfo:
            paths_safety.validate_wipe_target(home)

        assert excinfo.value.path == home.resolve()
        assert excinfo.value.reason

    def test_cible_inexistante_leve(self, home: Path) -> None:
        missing = home / "Games" / "stalker-gamma"

        with pytest.raises(paths_safety.UnsafeWipeTargetError):
            paths_safety.validate_wipe_target(missing)

    def test_cas_nominal_retourne_le_chemin_resolu(self, home: Path) -> None:
        target = _install(home)

        assert paths_safety.validate_wipe_target(target) == target.resolve()


class TestUnsafeChildNameReason:
    """Validation pure du **nom** d'une entrée à supprimer (T12, `verify --repair`)."""

    @pytest.mark.parametrize("name", ["", "   ", ".", "..", "../etc", "a/b", "a\\b", "a\0b"])
    def test_noms_qui_sechappent_refuses(self, name: str) -> None:
        assert paths_safety.unsafe_child_name_reason(name) is not None

    @pytest.mark.parametrize(
        "name",
        [
            "312- Gunslinger Guns for Anomaly - Teivazcz & Gunslinger Team",
            "..dossier-qui-commence-par-des-points",
            "mod.7z",
        ],
    )
    def test_noms_de_mods_legitimes_acceptes(self, name: str) -> None:
        assert paths_safety.unsafe_child_name_reason(name) is None


class TestValidateRemovableChild:
    @pytest.fixture
    def mods(self, tmp_path: Path) -> Path:
        mods_dir = tmp_path / "gamma" / "mods"
        mods_dir.mkdir(parents=True)
        return mods_dir

    def test_cas_nominal_retourne_le_chemin_resolu(self, mods: Path) -> None:
        (mods / "101- Un mod").mkdir()

        resolved = paths_safety.validate_removable_child(mods, "101- Un mod")

        assert resolved == (mods / "101- Un mod").resolve()

    def test_entree_absente_retourne_none(self, mods: Path) -> None:
        assert paths_safety.validate_removable_child(mods, "jamais-installe") is None

    @pytest.mark.parametrize("name", ["..", "../..", "sous/dossier", "..\\ailleurs"])
    def test_nom_qui_sechappe_leve(self, mods: Path, name: str) -> None:
        with pytest.raises(paths_safety.UnsafeWipeTargetError):
            paths_safety.validate_removable_child(mods, name)

    def test_lien_symbolique_leve(self, mods: Path, tmp_path: Path) -> None:
        ailleurs = tmp_path / "precieux"
        ailleurs.mkdir()
        (mods / "faux-mod").symlink_to(ailleurs)

        with pytest.raises(paths_safety.UnsafeWipeTargetError):
            paths_safety.validate_removable_child(mods, "faux-mod")

    def test_lien_symbolique_casse_leve_au_lieu_de_none(self, mods: Path, tmp_path: Path) -> None:
        """`exists()` répond False sur un lien cassé : le refus doit primer."""
        (mods / "lien-casse").symlink_to(tmp_path / "disparu")

        with pytest.raises(paths_safety.UnsafeWipeTargetError):
            paths_safety.validate_removable_child(mods, "lien-casse")

    def test_parent_lui_meme_symlink_reste_accepte(self, tmp_path: Path) -> None:
        """`downloads/` est souvent un lien vers `cache/` : le parent, lui, peut l'être."""
        real = tmp_path / "cache"
        real.mkdir()
        (real / "mod.7z").write_bytes(b"x")
        downloads = tmp_path / "downloads"
        downloads.symlink_to(real)

        assert (
            paths_safety.validate_removable_child(downloads, "mod.7z")
            == (real / "mod.7z").resolve()
        )
