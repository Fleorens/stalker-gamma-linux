"""Rapport de diagnostic exportable (`report_bundle`).

L'enjeu principal est l'anonymisation : ce fichier est fait pour être collé sur
un ticket public, il ne doit pas y semer le nom de compte de l'utilisateur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux import report_bundle
from stalker_gamma_linux.doctor import DoctorReport
from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.prefix.doctor import PrefixReport
from stalker_gamma_linux.state import InstallState


def _doctor_report(target: Path) -> DoctorReport:
    return DoctorReport(
        target=target,
        environment=EnvironmentReport(
            distro=Distro(family=DistroFamily.FEDORA, pretty_name="Fedora Linux 44"),
            requirements=(Requirement(name="7z", status=Status.OK, detail="7z detected"),),
        ),
        prefix=PrefixReport(
            requirements=(Requirement(name="Proton", status=Status.OK, detail="GE-Proton11-1"),)
        ),
        install=InstallState(anomaly=True),
        installed_on_disk=True,
    )


class TestAnonymize:
    def test_le_home_devient_tilde(self) -> None:
        text = "/home/marie/Games/stalker-gamma et /home/marie/.config/x"

        result = report_bundle.anonymize(text, home=Path("/home/marie"))

        assert "marie" not in result
        assert result.count("~") == 2

    def test_racine_ignoree(self) -> None:
        """Un home à `/` remplacerait tout et rendrait le rapport illisible."""
        text = "/usr/bin/umu-run"

        assert report_bundle.anonymize(text, home=Path("/")) == text

    def test_texte_sans_home_inchange(self) -> None:
        text = "aucun chemin personnel ici"

        assert report_bundle.anonymize(text, home=Path("/home/marie")) == text


class TestBuildBundle:
    def test_contient_les_sections_attendues(self, tmp_path: Path) -> None:
        bundle = report_bundle.build_bundle(_doctor_report(tmp_path), log_tail="ligne de journal")

        for section in ("Report", "Environment", "Proton prefix", "Installation", "Log"):
            assert f"=== {section}" in bundle

    def test_contient_version_et_plateforme(self, tmp_path: Path) -> None:
        bundle = report_bundle.build_bundle(_doctor_report(tmp_path), log_tail="")

        assert report_bundle.DISTRIBUTION_NAME in bundle
        assert "Python" in bundle

    def test_le_journal_fourni_est_repris(self, tmp_path: Path) -> None:
        bundle = report_bundle.build_bundle(_doctor_report(tmp_path), log_tail="BOOM traceback")

        assert "BOOM traceback" in bundle

    def test_le_home_nappara_it_pas(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bout en bout : la cible est sous le home, elle doit ressortir en `~`."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        target = tmp_path / "Games" / "stalker-gamma"

        bundle = report_bundle.build_bundle(_doctor_report(target), log_tail="")

        assert str(tmp_path) not in bundle
        assert "~/Games/stalker-gamma" in bundle


class TestRunReport:
    def test_ecrit_le_fichier(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            report_bundle, "build_full_report", lambda target: _doctor_report(tmp_path)
        )
        destination = tmp_path / "rapports" / "report.txt"

        assert report_bundle.run_report(tmp_path, destination) == 0
        assert "=== Report ===" in destination.read_text(encoding="utf-8")

    def test_destination_illisible_retourne_un(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            report_bundle, "build_full_report", lambda target: _doctor_report(tmp_path)
        )
        blocker = tmp_path / "fichier"
        blocker.write_text("je ne suis pas un dossier")

        assert report_bundle.run_report(tmp_path, blocker / "report.txt") == 1

    def test_sans_destination_ecrit_sur_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            report_bundle, "build_full_report", lambda target: _doctor_report(tmp_path)
        )

        assert report_bundle.run_report(tmp_path, None) == 0
        assert "=== Report ===" in capsys.readouterr().out


class TestVersionLine:
    """Identifier précisément le code qui tourne — l'enjeu du triage d'issues."""

    def test_sans_revision_enregistree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        line = report_bundle.version_line()

        assert report_bundle.DISTRIBUTION_NAME in line
        assert "(" not in line  # aucun suffixe de révision

    def test_avec_revision_enregistree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        revision_dir = tmp_path / report_bundle.DISTRIBUTION_NAME
        revision_dir.mkdir(parents=True)
        (revision_dir / "installed-revision.txt").write_text("a1b2c3d\n")

        assert "a1b2c3d" in report_bundle.version_line()

    def test_fichier_vide_ignore(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        revision_dir = tmp_path / report_bundle.DISTRIBUTION_NAME
        revision_dir.mkdir(parents=True)
        (revision_dir / "installed-revision.txt").write_text("\n")

        assert report_bundle.installed_revision() is None
