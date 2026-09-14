"""Cache de shaders DXVK/Mesa/NVIDIA (T21) : détection de pilote et variables posées."""

from pathlib import Path

import pytest

from stalker_gamma_linux.environment import shader_cache


def _patch_nvidia_markers(monkeypatch: pytest.MonkeyPatch, markers: tuple[Path, ...]) -> None:
    monkeypatch.setattr(shader_cache, "_NVIDIA_MARKERS", markers)


def _patch_mesa_dirs(monkeypatch: pytest.MonkeyPatch, dirs: tuple[Path, ...]) -> None:
    monkeypatch.setattr(shader_cache, "_MESA_ICD_DIRS", dirs)


def test_nvidia_present_true_when_a_marker_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    present = tmp_path / "version"
    present.write_text("x")
    _patch_nvidia_markers(monkeypatch, (tmp_path / "missing", present))

    assert shader_cache.nvidia_present() is True


def test_nvidia_present_false_when_no_marker_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_nvidia_markers(monkeypatch, (tmp_path / "missing-a", tmp_path / "missing-b"))

    assert shader_cache.nvidia_present() is False


def test_mesa_present_true_for_non_nvidia_icd_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    icd_dir = tmp_path / "icd.d"
    icd_dir.mkdir()
    (icd_dir / "radeon_icd.x86_64.json").write_text("{}")
    _patch_mesa_dirs(monkeypatch, (icd_dir,))

    assert shader_cache.mesa_present() is True


def test_mesa_present_false_when_only_nvidia_icd_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    icd_dir = tmp_path / "icd.d"
    icd_dir.mkdir()
    (icd_dir / "nvidia_icd.json").write_text("{}")
    _patch_mesa_dirs(monkeypatch, (icd_dir,))

    assert shader_cache.mesa_present() is False


def test_mesa_present_false_when_directories_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_mesa_dirs(monkeypatch, (tmp_path / "does-not-exist",))

    assert shader_cache.mesa_present() is False


def test_build_env_always_sets_dxvk_path_under_shaders_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shader_cache, "mesa_present", lambda: False)
    monkeypatch.setattr(shader_cache, "nvidia_present", lambda: False)

    env = shader_cache.build_env(Path("/root/cache/shaders"))

    assert env == {"DXVK_SHADER_CACHE_PATH": str(Path("/root/cache/shaders/dxvk"))}


def test_build_env_adds_mesa_vars_only_when_mesa_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shader_cache, "mesa_present", lambda: True)
    monkeypatch.setattr(shader_cache, "nvidia_present", lambda: False)

    env = shader_cache.build_env(Path("/root/cache/shaders"))

    assert env["MESA_SHADER_CACHE_DIR"] == str(Path("/root/cache/shaders/mesa"))
    assert env["MESA_SHADER_CACHE_MAX_SIZE"] == "10G"
    assert "__GL_SHADER_DISK_CACHE_PATH" not in env


def test_build_env_adds_nvidia_vars_only_when_nvidia_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shader_cache, "mesa_present", lambda: False)
    monkeypatch.setattr(shader_cache, "nvidia_present", lambda: True)

    env = shader_cache.build_env(Path("/root/cache/shaders"))

    assert env["__GL_SHADER_DISK_CACHE_PATH"] == str(Path("/root/cache/shaders/nvidia"))
    assert env["__GL_SHADER_DISK_CACHE_SIZE"] == str(10 * 1024**3)
    assert "MESA_SHADER_CACHE_DIR" not in env
