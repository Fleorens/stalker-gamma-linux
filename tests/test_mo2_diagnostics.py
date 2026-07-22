from pathlib import Path

from stalker_gamma_linux.mo2 import diagnostics
from stalker_gamma_linux.mo2.paths import Mo2Paths

_MODLIST_WITH_MODS = "+Mod A\n+Mod B\n-Mod C\n"


def _instance(tmp_path: Path, *, modlist: str | None = None) -> Mo2Paths:
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    if modlist is not None:
        profile = mo2.profile("G.A.M.M.A")
        profile.mkdir(parents=True)
        (profile / "modlist.txt").write_text(modlist, encoding="utf-8")
    return mo2


def _write_usvfs_log(mo2: Mo2Paths, name: str, content: str) -> Path:
    mo2.logs.mkdir(parents=True, exist_ok=True)
    log = mo2.logs / name
    log.write_text(content, encoding="utf-8")
    return log


def test_latest_usvfs_log_picks_most_recent_by_name(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path)
    _write_usvfs_log(mo2, "usvfs-2026-07-20_10-00-00.log", "old")
    newest = _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "new")

    assert diagnostics.latest_usvfs_log(mo2) == newest


def test_latest_usvfs_log_none_without_logs(tmp_path: Path) -> None:
    assert diagnostics.latest_usvfs_log(_instance(tmp_path)) is None


def test_diagnose_active_when_marker_present(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "...\nproxy run successful\n")

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is True
    assert result.enabled_mod_count == 2
    assert "USVFS actif" in result.message


def test_diagnose_dead_when_marker_absent_with_mods(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "started proxy\n(no success line)\n")

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.enabled_mod_count == 2
    assert "USVFS probablement mort" in result.message
    assert "MO2-PROTON-COMPAT.md" in result.message


def test_diagnose_dead_no_mods_gives_config_advice(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist="-All Off\n")
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "nothing useful\n")

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.enabled_mod_count == 0
    assert "Aucun mod activé" in result.message


def test_diagnose_no_log_reports_missing(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.checked_log is None
    assert "Aucun journal USVFS" in result.message


def test_usvfs_active_in_matches_marker() -> None:
    assert diagnostics.usvfs_active_in("blah\nproxy run successful\nblah") is True
    assert diagnostics.usvfs_active_in("blah\nfailed\nblah") is False
