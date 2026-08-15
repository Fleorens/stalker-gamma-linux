"""Commande `import` : adoption d'une installation GAMMA déjà sur le disque."""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux import adopt, state


def _make_install(root: Path, anomaly: str = "anomaly", gamma: str = "gamma") -> tuple[Path, Path]:
    """Crée une arborescence minimale reconnaissable (les deux marqueurs)."""
    anomaly_dir = root / anomaly
    gamma_dir = root / gamma
    anomaly_dir.mkdir(parents=True)
    gamma_dir.mkdir(parents=True)
    (anomaly_dir / adopt.ANOMALY_MARKER).write_text("", encoding="utf-8")
    (gamma_dir / adopt.MO2_MARKER).write_text("", encoding="utf-8")
    return anomaly_dir, gamma_dir


def test_discover_finds_both_markers(tmp_path: Path) -> None:
    anomaly_dir, gamma_dir = _make_install(tmp_path / "GAMMA")

    found = adopt.discover(tmp_path / "GAMMA")

    assert found.anomaly == anomaly_dir
    assert found.gamma == gamma_dir


def test_discover_reaches_a_nested_install(tmp_path: Path) -> None:
    # Cas réel d'un dossier de bibliothèque : `<source>/Games/GAMMA/{anomaly,gamma}`.
    anomaly_dir, _gamma = _make_install(tmp_path / "Games" / "GAMMA")

    assert adopt.discover(tmp_path).anomaly == anomaly_dir


def test_discover_prefers_the_shallowest_anomaly(tmp_path: Path) -> None:
    # Le layout GAMMA tolère un `anomaly/` imbriqué dans l'instance : celui de
    # la racine est la vraie installation, c'est lui qu'il faut adopter.
    root = tmp_path / "GAMMA"
    anomaly_dir, gamma_dir = _make_install(root)
    nested = gamma_dir / "anomaly"
    nested.mkdir()
    (nested / adopt.ANOMALY_MARKER).write_text("", encoding="utf-8")

    assert adopt.discover(root).anomaly == anomaly_dir


def test_discover_explains_what_is_missing(tmp_path: Path) -> None:
    lonely = tmp_path / "anomaly"
    lonely.mkdir()
    (lonely / adopt.ANOMALY_MARKER).write_text("", encoding="utf-8")

    with pytest.raises(adopt.AdoptionError) as excinfo:
        adopt.discover(tmp_path)

    assert adopt.MO2_MARKER in str(excinfo.value)
    assert "--source" in str(excinfo.value)


def test_discover_rejects_a_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(adopt.AdoptionError):
        adopt.discover(file_path)


def test_plan_adopts_a_standard_layout_in_place(tmp_path: Path) -> None:
    # `<racine>/anomaly` + `<racine>/gamma` : rien à lier, on adopte la racine.
    root = tmp_path / "GAMMA"
    _make_install(root)

    adoption = adopt.plan(adopt.discover(root))

    assert adoption.root == root
    assert adoption.is_in_place


def test_plan_links_a_non_standard_layout(tmp_path: Path) -> None:
    source = tmp_path / "heroic" / "STALKER GAMMA"
    anomaly_dir, gamma_dir = _make_install(source, anomaly="Anomaly", gamma="GAMMA")
    target = tmp_path / "Games" / "stalker-gamma"

    adoption = adopt.plan(adopt.discover(source), target)

    assert adoption.root == target
    assert adoption.links == (
        (target / "anomaly", anomaly_dir),
        (target / "gamma", gamma_dir),
    )


def test_apply_creates_symlinks_without_copying(tmp_path: Path) -> None:
    source = tmp_path / "gog"
    anomaly_dir, gamma_dir = _make_install(source, anomaly="Anomaly", gamma="GAMMA")
    target = tmp_path / "target"

    adoption = adopt.plan(adopt.discover(source), target)
    adopt.apply(adoption, on_progress=lambda _line: None)

    assert (target / "anomaly").is_symlink()
    assert (target / "anomaly").resolve() == anomaly_dir.resolve()
    assert (target / "gamma").resolve() == gamma_dir.resolve()
    # Aucune copie : les fichiers d'origine restent l'unique exemplaire.
    assert (target / "anomaly" / adopt.ANOMALY_MARKER).is_file()


def test_apply_marks_only_the_download_steps_as_done(tmp_path: Path) -> None:
    # Le préfixe, l'instance MO2, ReShade et le raccourci restent à faire :
    # rien ne dit qu'ils l'ont été sur l'installation adoptée.
    root = tmp_path / "GAMMA"
    _make_install(root)

    adopt.apply(adopt.plan(adopt.discover(root)), on_progress=lambda _line: None)

    persisted = state.load_state(root)
    assert persisted.anomaly and persisted.gamma
    assert not persisted.reshade
    assert not persisted.prefix
    assert not persisted.mo2
    assert not persisted.shortcut


def test_import_is_replayable(tmp_path: Path) -> None:
    source = tmp_path / "gog"
    _make_install(source, anomaly="Anomaly", gamma="GAMMA")
    target = tmp_path / "target"

    assert adopt.run_import(source, target, on_progress=lambda _line: None) == 0
    assert adopt.run_import(source, target, on_progress=lambda _line: None) == 0


def test_import_refuses_to_replace_an_existing_directory(tmp_path: Path) -> None:
    source = tmp_path / "gog"
    _make_install(source, anomaly="Anomaly", gamma="GAMMA")
    target = tmp_path / "target"
    (target / "anomaly").mkdir(parents=True)
    (target / "anomaly" / "precious.bin").write_text("", encoding="utf-8")

    lines: list[str] = []
    code = adopt.run_import(source, target, on_progress=lines.append)

    assert code == 1
    assert (target / "anomaly" / "precious.bin").is_file()
    assert "already exists" in "\n".join(lines)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "gog"
    _make_install(source, anomaly="Anomaly", gamma="GAMMA")
    target = tmp_path / "target"

    code = adopt.run_import(source, target, dry_run=True, on_progress=lambda _line: None)

    assert code == 0
    assert not target.exists()
    assert not state.load_state(target).anomaly


def test_import_points_at_the_command_that_finishes_the_job(tmp_path: Path) -> None:
    root = tmp_path / "GAMMA"
    _make_install(root)
    lines: list[str] = []

    adopt.run_import(root, on_progress=lines.append)

    output = "\n".join(lines)
    assert f"install --target {root}" in output
    assert "re-downloaded" in output
