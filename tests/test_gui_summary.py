"""Résumé « système prêt ? » de l'accueil (`gui.summary`)."""

from __future__ import annotations

from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.gui.summary import summarize

_DISTRO = Distro(family=DistroFamily.FEDORA, pretty_name="Fedora Test")


def _report(*requirements: Requirement) -> EnvironmentReport:
    return EnvironmentReport(distro=_DISTRO, requirements=requirements)


def _req(name: str, status: Status) -> Requirement:
    return Requirement(name=name, status=status, detail="détail")


class TestSummarize:
    def test_tout_ok(self) -> None:
        result = summarize(_report(_req("Steam", Status.OK), _req("umu", Status.OK)))
        assert result.is_ready
        assert result.label == "System ready"

    def test_unavailable_ne_bloque_pas(self) -> None:
        result = summarize(_report(_req("GPU Vulkan", Status.UNAVAILABLE)))
        assert result.is_ready

    def test_un_seul_manquant_est_nomme(self) -> None:
        result = summarize(
            _report(_req("Steam", Status.OK), _req("umu-launcher", Status.MISSING))
        )
        assert not result.is_ready
        assert result.label == "Missing prerequisite: umu-launcher"

    def test_plusieurs_manquants_sont_comptes(self) -> None:
        result = summarize(
            _report(
                _req("Steam", Status.MISSING),
                _req("umu-launcher", Status.MISSING),
                _req("7z", Status.OUTDATED),
            )
        )
        assert result.label == "3 missing prerequisites"
        assert result.blocking == ("Steam", "umu-launcher", "7z")
