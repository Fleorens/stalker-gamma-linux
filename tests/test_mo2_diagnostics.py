from pathlib import Path

import pytest

from stalker_gamma_linux.mo2 import diagnostics
from stalker_gamma_linux.mo2.paths import Mo2Paths

_MODLIST_WITH_MODS = "+Mod A\n+Mod B\n-Mod C\n"

# Extrait réel de ~/.local/state/stalker-gamma-linux/stalker-gamma-linux.log
# (pose des verbs winetricks sur un préfixe sain) : sert de log "sain" — il
# mentionne "concrt140" en texte libre (sans ".dll") et ne doit déclencher
# aucun faux positif du diagnostic runtime/préfixe.
_HEALTHY_LAUNCH_LOG = (
    "$ umu-run ModOrganizer.exe moshortcut://:Anomaly (DX11)\n"
    "Using native,builtin override for following DLLs: concrt140 msvcp140 "
    "msvcp140_1 msvcp140_2 msvcp140_atomic_wait msvcp140_codecvt_ids vcamp140 "
    "vccorlib140 vcomp140 vcruntime140\n"
    "inithooks in process 692 successful\n"
)

# Reconstruits à partir des formats d'erreur Wine documentés (pas de tel échec
# capturé sous ~/.local/state/stalker-gamma-linux/ au moment d'écrire ces tests).
_CONCRT140_LAUNCH_LOG = (
    "$ umu-run ModOrganizer.exe\n"
    "0009:err:module:import_dll Library concrt140.dll (which is needed by "
    'L"Z:\\\\mnt\\\\...\\\\ModOrganizer.exe") not found\n'
    "0009:err:module:import_dll Library ModOrganizer.exe not found\n"
)

_VERSION_MISMATCH_LAUNCH_LOG = (
    "$ umu-run ModOrganizer.exe\n"
    "wine client error:0: version mismatch, 787 != 774\n"
    "wine: wineserver has terminated, unable to continue\n"
)

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
    assert "USVFS active" in result.message


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
    assert "USVFS may be inactive" in result.message
    assert "MO2-PROTON-COMPAT.md" in result.message


def test_diagnose_dead_no_mods_gives_config_advice(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist="-All Off\n")
    _write_usvfs_log(mo2, "usvfs-2026-07-22_18-00-00.log", "nothing useful\n")

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.enabled_mod_count == 0
    assert "No mod enabled" in result.message


def test_diagnose_no_log_reports_missing(tmp_path: Path) -> None:
    mo2 = _instance(tmp_path, modlist=_MODLIST_WITH_MODS)

    result = diagnostics.diagnose_usvfs(mo2)

    assert result.active is False
    assert result.checked_log is None
    assert "No USVFS log" in result.message


def test_usvfs_active_in_matches_real_markers() -> None:
    assert diagnostics.usvfs_active_in("x\ninithooks in process 42 successful\ny") is True
    assert diagnostics.usvfs_active_in("x\nmapping file in vfs: z:\\a, Z:\\a\ny") is True
    # Faux négatif historique : ce marqueur de forum ne doit plus être requis.
    assert diagnostics.usvfs_active_in("x\nproxy run successful\ny") is False
    assert diagnostics.usvfs_active_in("x\ninithooks in process 42 failed\ny") is False


class TestLaunchFailureDiagnosis:
    """Échecs runtime/préfixe reconnus EN AMONT de l'USVFS (mo2-game-*.log)."""

    def test_concrt140_reports_missing_vcruntime_and_repair_command(self) -> None:
        message = diagnostics.launch_failure_diagnosis(_CONCRT140_LAUNCH_LOG)

        assert message is not None
        assert "VC++ runtime" in message
        assert "prefix-doctor --repair" in message

    @pytest.mark.parametrize("dll", ["msvcp140.dll", "vcruntime140.dll", "CONCRT140.DLL"])
    def test_other_vcruntime_dlls_and_case_insensitivity(self, dll: str) -> None:
        assert diagnostics.launch_failure_diagnosis(f"error: {dll} not found") is not None

    @pytest.mark.parametrize(
        "marker",
        [
            "wine client error:0: version mismatch, 787 != 774",
            "wrong wineserver",
            "prefix has an invalid version",
            "your wine binary was not upgraded correctly",
            "VERSION MISMATCH",
        ],
    )
    def test_proton_version_mismatch_markers(self, marker: str) -> None:
        message = diagnostics.launch_failure_diagnosis(marker)

        assert message is not None
        assert "install --only prefix" in message

    def test_version_mismatch_reports_other_proton_build(self) -> None:
        message = diagnostics.launch_failure_diagnosis(_VERSION_MISMATCH_LAUNCH_LOG)

        assert message is not None
        assert "install --only prefix" in message

    def test_healthy_launch_log_is_not_a_false_positive(self) -> None:
        assert diagnostics.launch_failure_diagnosis(_HEALTHY_LAUNCH_LOG) is None

    def test_diagnose_launch_log_none_path_returns_none(self) -> None:
        assert diagnostics.diagnose_launch_log(None) is None

    def test_diagnose_launch_log_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert diagnostics.diagnose_launch_log(tmp_path / "missing.log") is None

    def test_diagnose_launch_log_reads_and_diagnoses(self, tmp_path: Path) -> None:
        log = tmp_path / "mo2-game-20260722-180000.log"
        log.write_text(_CONCRT140_LAUNCH_LOG, encoding="utf-8")

        message = diagnostics.diagnose_launch_log(log)

        assert message is not None
        assert "prefix-doctor --repair" in message
