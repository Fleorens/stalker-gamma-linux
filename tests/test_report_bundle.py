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
from stalker_gamma_linux.postmortem.outcome import SessionEnd, SessionOutcome
from stalker_gamma_linux.postmortem.result import Finding, Postmortem
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

    def test_cible_hors_du_home_anonymise_le_compte(self) -> None:
        """Cas réel : `--target /mnt/jeux/<user>/gamma`, hors du home."""
        text = "Target: /mnt/jeux/marie/gamma"

        result = report_bundle.anonymize(text, home=Path("/home/marie"), user="marie", uid=1000)

        assert "marie" not in result

    def test_run_user_uid_masque(self) -> None:
        text = "XDG_RUNTIME_DIR=/run/user/1000 (umu-run)"

        result = report_bundle.anonymize(text, home=Path("/home/marie"), user="marie", uid=1000)

        assert "/run/user/1000" not in result
        assert "/run/user/~" in result

    def test_compte_court_ignore_sans_corrompre_le_rapport(self) -> None:
        """Un compte de 2 caractères écraserait « GE-Proton11-1 » via `\\b` : on

        préfère ne pas le réécrire du tout plutôt que de casser le rapport.
        """
        text = "Proton: GE-Proton11-1 — ge-perso-tool aussi présent"

        result = report_bundle.anonymize(text, home=Path("/home/ge"), user="ge", uid=1000)

        assert result == text

    def test_nom_de_compte_nu_hors_home_est_masque(self) -> None:
        """`/media/<user>/…` ne contient pas le home : seul le remplacement du

        nom de compte nu peut l'anonymiser.
        """
        text = "/media/marie/DisqueExterne/gamma"

        result = report_bundle.anonymize(text, home=Path("/home/marie"), user="marie", uid=1000)

        assert "marie" not in result

    def test_compte_ne_corrompt_pas_une_sous_chaine_alphanumerique(self) -> None:
        """Frontières de mot : un compte "ana" ne doit pas mordre sur "banana"."""
        text = "un fruit : banana"

        result = report_bundle.anonymize(text, home=Path("/home/ana"), user="ana", uid=1000)

        assert result == text


class TestBuildBundle:
    def test_contient_les_sections_attendues(self, tmp_path: Path) -> None:
        bundle = report_bundle.build_bundle(_doctor_report(tmp_path), log_tail="ligne de journal")

        for section in (
            "Report",
            "Environment",
            "Proton prefix",
            "Installation",
            "Post-mortem",
            "Log",
        ):
            assert f"=== {section}" in bundle

    def test_le_verdict_du_post_mortem_est_repris(self, tmp_path: Path) -> None:
        """Le post-mortem et son extrait de trace font la moitié d'un ticket
        utile : sans eux, on redemande le journal à chaque issue."""
        postmortem = Postmortem(
            finding=Finding.ENGINE_CRASH,
            root=tmp_path,
            session=SessionEnd(
                outcome=SessionOutcome.ENGINE_CRASH,
                excerpt=("stack trace:", "at address 0x0000000140B02DC1"),
            ),
        )

        bundle = report_bundle.build_bundle(
            _doctor_report(tmp_path), log_tail="", postmortem=postmortem
        )

        assert "The engine crashed" in bundle
        assert "at address 0x0000000140B02DC1" in bundle

    def test_le_post_mortem_passe_par_lanonymisation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un journal X-Ray recopie le chemin complet de l'install à chaque ligne
        de son dump de crash — donc le nom de compte."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        postmortem = Postmortem(
            finding=Finding.ENGINE_CRASH,
            root=tmp_path,
            session=SessionEnd(
                outcome=SessionOutcome.ENGINE_CRASH,
                excerpt=(f"SymInit: Symbol-SearchPath: '{tmp_path}/Games/GAMMA/anomaly/bin'",),
            ),
        )

        bundle = report_bundle.build_bundle(
            _doctor_report(tmp_path), log_tail="", postmortem=postmortem
        )

        assert str(tmp_path) not in bundle
        assert "~/Games/GAMMA/anomaly/bin" in bundle

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
