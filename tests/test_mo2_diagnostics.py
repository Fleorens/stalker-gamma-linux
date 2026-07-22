from pathlib import Path

from stalker_gamma_linux.mo2 import diagnostics
from stalker_gamma_linux.mo2.paths import Mo2Paths

_MODLIST_WITH_MODS = "+Mod A\n+Mod B\n-Mod C\n"

# Extrait d'un vrai log usvfs 0.5.6.1 (GE-Proton11-1) sur un run modé qui marche.
_LIVE_USVFS_LOG = (
    "usvfs dll 0.5.6.1 initialized in process 324\n"
    "mod_organizer_instance_1 created in process 324\n"
    "hooked NtCreateFile (0x...) in C:\\windows\\system32\\ntdll.dll type overwrite\n"
    "failed to hook NtQueryDirectoryFileEx: No Error\n"
    "inithooks in process 692 successful\n"
    "mapping file in vfs: z:\\mnt\\...\\anomaly\\appdata\\..., Z:\\mnt\\...\n"
    "releasing hook context\n"
)


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


def test_diagnose_active_on_real_live_log(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", _LIVE_USVFS_LOG)

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is True
    assert result.enabled_mod_count == 2
    assert "USVFS actif" in result.message


def test_diagnose_active_from_inithooks_alone(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "inithooks in process 692 successful\n")

    assert diagnostics.diagnose_usvfs(mo2).active is True


def test_diagnose_active_from_vfs_mapping_alone(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "mapping file in vfs: z:\\x, Z:\\x\n")

    assert diagnostics.diagnose_usvfs(mo2).active is True


def test_diagnose_dead_when_marker_absent_with_mods(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "started proxy\n(no success line)\n")

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.enabled_mod_count == 2
    assert "USVFS peut-être inactif" in result.message
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


def test_usvfs_active_in_matches_real_markers() -> None:
    assert diagnostics.usvfs_active_in("x\ninithooks in process 42 successful\ny") is True
    assert diagnostics.usvfs_active_in("x\nmapping file in vfs: z:\\a, Z:\\a\ny") is True
    # Faux négatif historique : ce marqueur de forum ne doit plus être requis.
    assert diagnostics.usvfs_active_in("x\nproxy run successful\ny") is False
    assert diagnostics.usvfs_active_in("x\ninithooks in process 42 failed\ny") is False
