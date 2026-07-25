"""Modèle immuable de timeline de phases (`gui.phases`)."""

from __future__ import annotations

from stalker_gamma_linux.gui.phases import PhaseStatus, Timeline
from stalker_gamma_linux.gui.worker import ReporterEvent

LABELS = ("Anomaly", "Modpack", "Préfixe")


def _timeline() -> Timeline:
    return Timeline.from_labels(LABELS)


class TestConstruction:
    def test_toutes_les_phases_en_attente(self) -> None:
        timeline = _timeline()
        assert [phase.status for phase in timeline.phases] == [PhaseStatus.PENDING] * 3
        assert timeline.fraction == 0.0
        assert not timeline.has_failure


class TestStep:
    def test_demarre_la_phase_indexee(self) -> None:
        timeline = _timeline().apply(ReporterEvent("step", "Anomaly…", index="1/3"))
        assert timeline.phases[0].status is PhaseStatus.RUNNING
        assert timeline.phases[1].status is PhaseStatus.PENDING

    def test_les_precedentes_passent_a_fait(self) -> None:
        timeline = _timeline().apply(ReporterEvent("step", "Préfixe…", index="3/3"))
        assert [phase.status for phase in timeline.phases] == [
            PhaseStatus.DONE,
            PhaseStatus.DONE,
            PhaseStatus.RUNNING,
        ]

    def test_une_phase_sautee_reste_sautee(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("skip", "Anomaly", index="1/3"))
            .apply(ReporterEvent("step", "Préfixe…", index="3/3"))
        )
        assert timeline.phases[0].status is PhaseStatus.SKIPPED

    def test_index_illisible_est_neutre(self) -> None:
        before = _timeline()
        after = before.apply(ReporterEvent("step", "…", index="n/a"))
        assert after == before

    def test_index_hors_bornes_est_neutre(self) -> None:
        before = _timeline()
        after = before.apply(ReporterEvent("step", "…", index="4/4"))
        assert after == before

    def test_immutabilite(self) -> None:
        before = _timeline()
        before.apply(ReporterEvent("step", "Anomaly…", index="1/3"))
        assert all(phase.status is PhaseStatus.PENDING for phase in before.phases)


class TestProgressDetail:
    def test_va_sur_la_phase_en_cours(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("step", "Modpack…", index="2/3"))
            .apply(ReporterEvent("progress", "téléchargement 12/340"))
        )
        assert timeline.phases[1].detail == "téléchargement 12/340"
        assert timeline.phases[0].detail is None

    def test_garde_la_derniere_ligne_dun_message_multiligne(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("step", "Modpack…", index="2/3"))
            .apply(ReporterEvent("progress", "ligne 1\nligne 2"))
        )
        assert timeline.phases[1].detail == "ligne 2"

    def test_sans_phase_en_cours_est_neutre(self) -> None:
        before = _timeline()
        assert before.apply(ReporterEvent("progress", "…")) == before


class TestErreurEtFin:
    def test_erreur_marque_la_phase_en_cours(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("step", "Modpack…", index="2/3"))
            .apply(ReporterEvent("error", "boom"))
        )
        assert timeline.phases[1].status is PhaseStatus.FAILED
        assert timeline.has_failure

    def test_success_termine_tout_sauf_saute_et_echec(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("skip", "Anomaly", index="1/3"))
            .apply(ReporterEvent("step", "Modpack…", index="2/3"))
            .apply(ReporterEvent("success", "fini"))
        )
        assert [phase.status for phase in timeline.phases] == [
            PhaseStatus.SKIPPED,
            PhaseStatus.DONE,
            PhaseStatus.DONE,
        ]

    def test_complete_efface_le_detail(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("step", "Modpack…", index="2/3"))
            .apply(ReporterEvent("progress", "en cours"))
            .complete()
        )
        assert all(phase.detail is None for phase in timeline.phases)


class TestFraction:
    def test_demi_credit_pour_la_phase_en_cours(self) -> None:
        timeline = _timeline().apply(ReporterEvent("step", "Anomaly…", index="1/3"))
        assert timeline.fraction == 0.5 / 3

    def test_sautees_comptent_comme_faites(self) -> None:
        timeline = (
            _timeline()
            .apply(ReporterEvent("skip", "Anomaly", index="1/3"))
            .apply(ReporterEvent("skip", "Modpack", index="2/3"))
        )
        assert timeline.fraction == 2 / 3

    def test_timeline_vide(self) -> None:
        assert Timeline.from_labels(()).fraction == 0.0
