import threading
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux import engine, orchestrator, state
from stalker_gamma_linux.backups.errors import BackupWriteError
from stalker_gamma_linux.engine.errors import EngineCancelledError, EngineExecutionError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import (
    EnvironmentReport,
    Requirement,
    Status,
)
from stalker_gamma_linux.mo2 import instance, modlist_sync
from stalker_gamma_linux.prefix import provision, session
from stalker_gamma_linux.prefix.proton import ProtonBuild
from tests.conftest import RecordingReporter


def _patch_engine(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    for name in ("install_anomaly", "install_gamma", "remove_reshade", "purge_shader_cache"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: lambda *a, **k: events.append(label))(name),
        )


def _patch_prefix_and_mo2(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    fake_build = ProtonBuild(name="GE-Proton10-1", path=Path("/opt/GE"), version=(10, 1))

    def fake_ensure_prefix(*a: Any, **k: Any) -> ProtonBuild:
        events.append("ensure_prefix")
        return fake_build

    monkeypatch.setattr(provision, "ensure_prefix", fake_ensure_prefix)
    monkeypatch.setattr(orchestrator, "resolve_anomaly", lambda mo2, install: install.anomaly)
    monkeypatch.setattr(
        instance,
        "configure_instance",
        lambda *a, **k: events.append("configure_instance"),
    )


def _patch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environnement système sain, indépendant de la machine qui exécute les tests.

    `run_install` refuse désormais de démarrer si un prérequis bloquant manque
    (7z, libunrar, umu, espace disque). Sans ce stub, la suite passerait ou
    échouerait selon l'espace libre du disque du développeur — ce qu'elle faisait
    déjà, silencieusement, avant que le blocage ne rende la dépendance visible.
    """
    monkeypatch.setattr(
        orchestrator,
        "build_report",
        lambda target: EnvironmentReport(
            distro=Distro(family=DistroFamily.FEDORA, pretty_name="Fedora Linux 44"),
            requirements=(Requirement(name="7z", status=Status.OK, detail="7z detected"),),
        ),
    )


def _patch_all(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    _patch_environment(monkeypatch)
    _patch_engine(monkeypatch, events)
    _patch_prefix_and_mo2(monkeypatch, events)


def test_run_install_runs_full_pipeline_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)

    code = orchestrator.run_install(tmp_path)

    assert code == 0
    assert events == [
        "install_anomaly",
        "install_gamma",
        "remove_reshade",
        "purge_shader_cache",
        "ensure_prefix",
        "configure_instance",
    ]


def test_run_install_passes_install_paths_under_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    events: list[str] = []

    def fake_anomaly(paths: InstallPaths, **kw: Any) -> None:
        captured["paths"] = paths

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", fake_anomaly)

    orchestrator.run_install(tmp_path)

    assert captured["paths"] == InstallPaths.under(tmp_path)


def test_run_install_returns_one_on_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("full-install", 1, "ModDB download link not found")

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", lambda *a, **k: None)
    monkeypatch.setattr(engine, "install_gamma", boom)

    assert orchestrator.run_install(tmp_path) == 1


def test_run_install_persists_progress_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("full-install", 1, "boom")

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", lambda *a, **k: None)
    monkeypatch.setattr(engine, "install_gamma", boom)

    orchestrator.run_install(tmp_path)

    result = state.load_state(tmp_path)
    assert result.is_done("anomaly")
    assert not result.is_done("gamma")


def test_run_install_skips_steps_already_marked_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    state.mark_done(tmp_path, "anomaly")
    state.mark_done(tmp_path, "gamma")
    state.mark_done(tmp_path, "reshade")

    code = orchestrator.run_install(tmp_path)

    assert code == 0
    assert events == ["ensure_prefix", "configure_instance"]


def test_run_install_creates_shortcut_only_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    monkeypatch.setattr(
        orchestrator, "install_shortcut", lambda target: events.append("install_shortcut")
    )

    orchestrator.run_install(tmp_path, shortcut=False)
    assert "install_shortcut" not in events
    assert not state.load_state(tmp_path).is_done("shortcut")

    orchestrator.run_install(tmp_path, shortcut=True)
    assert "install_shortcut" in events
    assert state.load_state(tmp_path).is_done("shortcut")


def test_run_update_runs_pipeline_in_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    for name in ("update_gamma", "remove_reshade", "purge_shader_cache", "verify"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: lambda *a, **k: events.append(label))(name),
        )

    code = orchestrator.run_update(tmp_path)

    assert code == 0
    assert events == ["update_gamma", "remove_reshade", "purge_shader_cache", "verify"]
    assert state.load_state(tmp_path).is_done("gamma")


def test_run_update_returns_one_on_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("check-md5", 1, "fichier corrompu")

    monkeypatch.setattr(engine, "update_gamma", lambda *a, **k: None)
    monkeypatch.setattr(engine, "remove_reshade", lambda *a, **k: None)
    monkeypatch.setattr(engine, "purge_shader_cache", lambda *a, **k: None)
    monkeypatch.setattr(engine, "verify", boom)

    assert orchestrator.run_update(tmp_path) == 1


def test_run_update_warns_on_unverifiable_archives_but_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entrées invérifiables en ligne (ModDB) = avertissement, pas un échec."""
    for name in ("update_gamma", "remove_reshade", "purge_shader_cache"):
        monkeypatch.setattr(engine, name, lambda *a, **k: None)
    monkeypatch.setattr(
        engine,
        "verify",
        lambda *a, **k: ("Could not find Filename in https://moddb/x",),
    )
    reporter = _RecordingReporter()

    code = orchestrator.run_update(tmp_path, reporter=reporter)

    assert code == 0
    warnings = [message for kind, message in reporter.events if kind == "warn"]
    assert len(warnings) == 1
    assert "no local corruption" in warnings[0]
    assert "Could not find Filename in https://moddb/x" in warnings[0]


def test_run_update_refuses_when_mo2_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        session,
        "prefix_in_use",
        lambda paths: session.ProcessHold(pid=42, name="Mod Organizer 2", what_to_close="it"),
    )
    for name in ("update_gamma", "remove_reshade", "purge_shader_cache", "verify"):
        monkeypatch.setattr(engine, name, lambda *a, **k: None)
    reporter = _RecordingReporter()

    code = orchestrator.run_update(tmp_path, reporter=reporter)

    assert code == 1
    errors = [message for kind, message in reporter.events if kind == "error"]
    assert len(errors) == 1
    assert "42" in errors[0]
    assert "Mod Organizer 2" in errors[0]


def test_run_update_force_bypasses_busy_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        session,
        "prefix_in_use",
        lambda paths: session.ProcessHold(pid=42, name="Mod Organizer 2", what_to_close="it"),
    )
    events: list[str] = []
    for name in ("update_gamma", "remove_reshade", "purge_shader_cache", "verify"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: lambda *a, **k: events.append(label))(name),
        )

    code = orchestrator.run_update(tmp_path, force=True)

    assert code == 0
    assert events == ["update_gamma", "remove_reshade", "purge_shader_cache", "verify"]


def test_run_install_only_prefix_refuses_when_mo2_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    monkeypatch.setattr(
        session,
        "prefix_in_use",
        lambda paths: session.ProcessHold(pid=7, name="the game (Anomaly)", what_to_close="it"),
    )
    state.mark_done(tmp_path, "anomaly")
    state.mark_done(tmp_path, "gamma")
    state.mark_done(tmp_path, "reshade")
    state.mark_done(tmp_path, "mo2")

    code = orchestrator.run_install(tmp_path, only=["prefix"])

    assert code == 1
    assert "ensure_prefix" not in events


def test_run_install_only_prefix_force_bypasses_busy_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    monkeypatch.setattr(
        session,
        "prefix_in_use",
        lambda paths: session.ProcessHold(pid=7, name="the game (Anomaly)", what_to_close="it"),
    )
    state.mark_done(tmp_path, "anomaly")
    state.mark_done(tmp_path, "gamma")
    state.mark_done(tmp_path, "reshade")
    state.mark_done(tmp_path, "mo2")

    code = orchestrator.run_install(tmp_path, only=["prefix"], force=True)

    assert code == 0
    assert "ensure_prefix" in events


class _RecordingReporter:
    """`output.Reporter` de test : enregistre les événements au lieu de les imprimer."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def header(self, message: str) -> None:
        self.events.append(("header", message))

    def step(self, index: str, message: str) -> None:
        self.events.append(("step", message))

    def skip(self, index: str, message: str) -> None:
        self.events.append(("skip", message))

    def progress(self, message: str) -> None:
        self.events.append(("progress", message))

    def success(self, message: str) -> None:
        self.events.append(("success", message))

    def warn(self, message: str) -> None:
        self.events.append(("warn", message))

    def error(self, message: str, *, hint: str | None = None) -> None:
        self.events.append(("error", message))


def test_run_install_uses_custom_reporter_instead_of_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    reporter = _RecordingReporter()

    code = orchestrator.run_install(tmp_path, reporter=reporter)

    assert code == 0
    assert ("header", f"Installing S.T.A.L.K.E.R. G.A.M.M.A. in {tmp_path}") in (reporter.events)
    assert any(kind == "success" for kind, _ in reporter.events)
    assert any(kind == "step" for kind, _ in reporter.events)


def test_run_install_stops_cleanly_when_cancel_event_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    cancel_event = threading.Event()
    cancel_event.set()
    reporter = _RecordingReporter()

    code = orchestrator.run_install(tmp_path, reporter=reporter, cancel_event=cancel_event)

    assert code == orchestrator.CANCELLED_EXIT_CODE
    assert events == []
    assert not state.load_state(tmp_path).is_done("anomaly")
    assert any(kind == "warn" and "cancelled" in message for kind, message in reporter.events)


def test_run_install_cancels_mid_step_without_marking_it_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un vrai appel `engine.*` annulé ne revient jamais normalement : le watchdog
    # (engine.process._watch_cancellation) tue le sous-process et `run()` lève
    # `EngineCancelledError` — le fake doit reproduire ce contrat, pas juste
    # positionner l'event et retourner (sinon `run_step` marquerait l'étape faite).
    events: list[str] = []
    cancel_event = threading.Event()

    def cancelling_install_anomaly(*a: Any, **k: Any) -> None:
        events.append("install_anomaly")
        cancel_event.set()
        raise EngineCancelledError("anomaly-install")

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", cancelling_install_anomaly)

    code = orchestrator.run_install(tmp_path, cancel_event=cancel_event)

    assert code == orchestrator.CANCELLED_EXIT_CODE
    assert events == ["install_anomaly"]
    assert not state.load_state(tmp_path).is_done("anomaly")


def test_run_update_stops_cleanly_on_engine_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def cancelled(*a: Any, **k: Any) -> None:
        raise EngineCancelledError("full-install")

    monkeypatch.setattr(engine, "update_gamma", cancelled)
    reporter = _RecordingReporter()

    code = orchestrator.run_update(tmp_path, reporter=reporter)

    assert code == orchestrator.CANCELLED_EXIT_CODE
    assert any(kind == "warn" and "cancelled" in message for kind, message in reporter.events)


def _report_with(*requirements: Requirement) -> EnvironmentReport:
    return EnvironmentReport(
        distro=Distro(family=DistroFamily.FEDORA, pretty_name="Fedora Linux 44"),
        requirements=requirements,
    )


class TestPrerequisMBloquants:
    """`install` doit refuser de partir plutôt que mourir 3 h plus tard."""

    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        report: EnvironmentReport,
        tmp_path: Path,
        **kwargs: Any,
    ) -> tuple[int, list[str]]:
        events: list[str] = []
        _patch_engine(monkeypatch, events)
        _patch_prefix_and_mo2(monkeypatch, events)
        monkeypatch.setattr(orchestrator, "build_report", lambda target: report)
        code = orchestrator.run_install(tmp_path, **kwargs)
        return code, events

    def test_espace_disque_insuffisant_arrete_avant_tout_telechargement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = _report_with(
            Requirement(name="Disk space", status=Status.MISSING, detail="10 GiB free")
        )

        code, events = self._run(monkeypatch, report, tmp_path)

        assert code == 1
        assert events == []  # rien n'a été lancé

    def test_force_passe_outre(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        report = _report_with(
            Requirement(name="Disk space", status=Status.MISSING, detail="10 GiB free")
        )

        code, events = self._run(monkeypatch, report, tmp_path, force=True)

        assert code == 0
        assert "install_anomaly" in events

    def test_gpu_vulkan_absent_ne_bloque_pas(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le GPU ne sert qu'à jouer : installer sans pilote doit rester possible."""
        report = _report_with(
            Requirement(
                name="Vulkan GPU",
                status=Status.MISSING,
                detail="no Vulkan device",
                needed_to_install=False,
            )
        )

        code, events = self._run(monkeypatch, report, tmp_path)

        assert code == 0
        assert "install_anomaly" in events

    def test_prerequis_facultatif_ne_bloque_pas(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        report = _report_with(
            Requirement(name="Steam", status=Status.OPTIONAL, detail="absent"),
            Requirement(name="Vulkan GPU", status=Status.UNAVAILABLE, detail="VM"),
        )

        code, _events = self._run(monkeypatch, report, tmp_path)

        assert code == 0


class TestSauvegardeAvantMiseAJour:
    """`full-install` écrase modlist.txt : la copie de secours n'est pas optionnelle.

    La copie elle-même vit désormais dans `backups/` (T17) — l'orchestrateur ne
    fait que l'appeler. Ce qu'on vérifie ici, c'est le contrat côté `run_update` :
    elle est posée **avant** que le moteur ne tourne, et son échec empêche la
    mise à jour.
    """

    def _profile(self, tmp_path: Path) -> Path:
        profile = tmp_path / "gamma" / "profiles" / "G.A.M.M.A"
        profile.mkdir(parents=True)
        (profile / "modlist.txt").write_text("+MonMod\n-ModDesactive\n")
        return profile

    def test_run_update_sauvegarde_avant_de_toucher_au_modpack(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = self._profile(tmp_path)
        seen: dict[str, str] = {}

        def fake_update(paths: Any, **kwargs: Any) -> None:
            # Au moment où le moteur tourne, la copie doit déjà exister.
            written = sorted((tmp_path / "backups").glob("profiles-*"))
            seen["backup"] = written[0].name if written else ""
            # …et le moteur est en droit d'écraser la liste juste après.
            (profile / "modlist.txt").write_text("+ListeAmont\n")

        monkeypatch.setattr(engine, "update_gamma", fake_update)
        monkeypatch.setattr(engine, "remove_reshade", lambda *a, **k: None)
        monkeypatch.setattr(engine, "purge_shader_cache", lambda *a, **k: None)
        monkeypatch.setattr(engine, "verify", lambda *a, **k: ())

        assert orchestrator.run_update(tmp_path) == 0
        assert seen["backup"].startswith("profiles-")
        restored = tmp_path / "backups" / seen["backup"] / "profiles" / "G.A.M.M.A" / "modlist.txt"
        assert restored.read_text() == "+MonMod\n-ModDesactive\n"

    def test_une_sauvegarde_impossible_annule_la_mise_a_jour(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._profile(tmp_path)
        touched: list[str] = []
        monkeypatch.setattr(engine, "update_gamma", lambda *a, **k: touched.append("engine"))
        monkeypatch.setattr(
            orchestrator.backups,
            "protect_before_update",
            _raise_backup_error,
        )
        reporter = _RecordingReporter()

        assert orchestrator.run_update(tmp_path, reporter=reporter) == 1
        assert touched == []
        assert any(kind == "error" for kind, _message in reporter.events)


def _raise_backup_error(root: Path, **kwargs: Any) -> None:
    raise BackupWriteError(root / "backups", OSError("No space left on device"))


def test_run_install_only_replays_the_named_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Cas de dépannage : « relance juste le préfixe et envoie-moi le journal ».
    events: list[str] = []
    _patch_all(monkeypatch, events)

    code = orchestrator.run_install(tmp_path, only=["prefix"])

    assert code == 0
    assert events == ["ensure_prefix"]


def test_run_install_only_ignores_the_done_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Rejouer une étape déjà marquée faite est tout l'intérêt du drapeau :
    # sans ça, `--only prefix` ne ferait rien sur une install complète.
    events: list[str] = []
    _patch_all(monkeypatch, events)
    state.mark_done(tmp_path, "prefix")

    orchestrator.run_install(tmp_path, only=["prefix"])

    assert events == ["ensure_prefix"]


def test_run_install_only_leaves_other_steps_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)

    orchestrator.run_install(tmp_path, only=["prefix"])

    persisted = state.load_state(tmp_path)
    assert persisted.prefix
    assert not persisted.anomaly
    assert not persisted.gamma


def test_run_install_only_accepts_several_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)

    orchestrator.run_install(tmp_path, only=["reshade", "mo2"])

    assert events == ["remove_reshade", "purge_shader_cache", "configure_instance"]


def test_run_install_only_shortcut_does_not_need_the_shortcut_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    monkeypatch.setattr(orchestrator, "install_shortcut", lambda root: events.append("shortcut"))

    orchestrator.run_install(tmp_path, only=["shortcut"])

    assert events == ["shortcut"]


def test_run_install_rejects_an_unknown_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)

    code = orchestrator.run_install(tmp_path, only=["prefixe"])

    assert code == 1
    assert events == []


class TestFusionDeLaModlist:
    """`update` rejoue les écarts du joueur sur la liste amont (T17, partie 2)."""

    def _profile(self, tmp_path: Path, text: str) -> Path:
        profile = tmp_path / "gamma" / "profiles" / "G.A.M.M.A"
        profile.mkdir(parents=True, exist_ok=True)
        modlist = profile / "modlist.txt"
        modlist.write_text(text, encoding="utf-8")
        return modlist

    def _engine_writes(self, monkeypatch: pytest.MonkeyPatch, modlist: Path, upstream: str) -> None:
        monkeypatch.setattr(
            engine, "update_gamma", lambda *a, **k: modlist.write_text(upstream, encoding="utf-8")
        )
        for name in ("remove_reshade", "purge_shader_cache"):
            monkeypatch.setattr(engine, name, lambda *a, **k: None)
        monkeypatch.setattr(engine, "verify", lambda *a, **k: ())

    def test_les_reglages_du_joueur_sont_rejoues_et_comptes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modlist_sync.write_snapshot(tmp_path, "+A\n+B\n+Retire\n")
        modlist = self._profile(tmp_path, "+A\n-B\n+MonMod\n+Retire\n")
        self._engine_writes(monkeypatch, modlist, "+A\n+B\n+Nouveau\n")
        reporter = _RecordingReporter()

        assert orchestrator.run_update(tmp_path, reporter=reporter) == 0
        assert modlist.read_text() == "+A\n-B\n+MonMod\n+Nouveau\n"
        text = "\n".join(message for _kind, message in reporter.events)
        assert "1 mod(s) re-enabled/disabled" in text
        assert "1 mod(s) you added put back in place" in text
        assert "1 entry(ies) removed upstream not restored" in text

    def test_no_merge_garde_le_comportement_historique(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modlist_sync.write_snapshot(tmp_path, "+A\n+B\n")
        modlist = self._profile(tmp_path, "+A\n-B\n+MonMod\n")
        self._engine_writes(monkeypatch, modlist, "+A\n+B\n+Nouveau\n")

        assert orchestrator.run_update(tmp_path, merge_modlist=False) == 0
        assert modlist.read_text() == "+A\n+B\n+Nouveau\n"
        # …mais la référence suit quand même l'amont, sinon la fusion suivante
        # comparerait à une liste périmée.
        assert modlist_sync.read_snapshot(tmp_path) == "+A\n+B\n+Nouveau\n"

    def test_sans_instantane_on_previent_au_lieu_de_deviner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modlist = self._profile(tmp_path, "+A\n-B\n")
        self._engine_writes(monkeypatch, modlist, "+A\n+B\n")
        reporter = _RecordingReporter()

        assert orchestrator.run_update(tmp_path, reporter=reporter) == 0
        assert modlist.read_text() == "+A\n+B\n"
        warnings = [message for kind, message in reporter.events if kind == "warn"]
        assert any("no upstream snapshot" in message for message in warnings)

    def test_une_install_neuve_ne_dit_rien_de_la_fusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Rien n'a été perdu : signaler une fusion impossible serait du bruit."""
        for name in ("update_gamma", "remove_reshade", "purge_shader_cache"):
            monkeypatch.setattr(engine, name, lambda *a, **k: None)
        monkeypatch.setattr(engine, "verify", lambda *a, **k: ())
        reporter = _RecordingReporter()

        assert orchestrator.run_update(tmp_path, reporter=reporter) == 0
        assert [message for kind, message in reporter.events if kind == "warn"] == []

    def test_les_etapes_sont_numerotees_sur_quatre_avec_fusion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modlist = self._profile(tmp_path, "+A\n")
        self._engine_writes(monkeypatch, modlist, "+A\n")
        # Le reporter partagé garde l'index « n/total », que celui de ce fichier
        # laisse tomber — et c'est exactement ce qu'on vérifie ici.
        reporter = RecordingReporter()

        orchestrator.run_update(tmp_path, reporter=reporter)

        steps = reporter.of_kind("step")
        assert [step.split()[0] for step in steps] == ["1/4", "2/4", "3/4", "4/4"]
        assert len(orchestrator.update_phase_labels()) == 4
        assert len(orchestrator.update_phase_labels(merge_modlist=False)) == 3

    def test_linstall_enregistre_la_reference_apres_le_moteur(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sans ça, la première mise à jour après une install ne saurait rien fusionner."""
        events: list[str] = []
        _patch_all(monkeypatch, events)
        profile = tmp_path / "gamma" / "profiles" / "G.A.M.M.A"
        profile.mkdir(parents=True)
        monkeypatch.setattr(
            engine,
            "install_gamma",
            lambda *a, **k: (profile / "modlist.txt").write_text("+Amont\n", encoding="utf-8"),
        )

        assert orchestrator.run_install(tmp_path) == 0
        assert modlist_sync.read_snapshot(tmp_path) == "+Amont\n"
