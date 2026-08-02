"""Rapport de diagnostic exportable (`doctor --report`), à joindre à une issue.

Sans ça, un utilisateur qui signale un problème doit copier-coller à la main la
sortie de `doctor`, retrouver le journal sous `~/.local/state/`, et penser à
préciser sa version et son build Proton — donc en pratique il n'envoie qu'un
tiers de ce qu'il faut, et chaque issue coûte deux ou trois allers-retours.

Ce module ne collecte rien de nouveau : `doctor.build_full_report` sépare déjà
la collecte du rendu, on ne fait que l'assembler avec la version du paquet, la
plate-forme et la fin du journal.

**Anonymisation** : tous les chemins sont réécrits en `~/…`. Le nom de compte
apparaît sinon des dizaines de fois dans un rapport destiné à un ticket public.
Ce n'est pas un anonymat fort — c'est le minimum décent quand on demande à
quelqu'un de coller un fichier sur GitHub.
"""

from __future__ import annotations

import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from stalker_gamma_linux import logging_setup
from stalker_gamma_linux import state as state_module
from stalker_gamma_linux.doctor import DoctorReport, build_full_report
from stalker_gamma_linux.environment.report import format_report
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix import proton
from stalker_gamma_linux.prefix.doctor import format_prefix_report

DISTRIBUTION_NAME = "stalker-gamma-linux"

# Assez pour couvrir l'échec et ce qui l'a précédé, sans transformer le rapport
# en dump de plusieurs mégaoctets que personne ne lira.
_LOG_TAIL_LINES = 200


def package_version() -> str:
    """Version installée, ou un marqueur explicite si le paquet n'est pas installé."""
    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:  # exécution depuis les sources, sans `pip install`
        return _("unknown (not installed as a package)")


def installed_revision() -> str | None:
    """Révision git réellement installée, telle qu'`install.sh` l'a enregistrée.

    Le numéro de version seul ne suffit pas à identifier le code qui tourne :
    entre deux releases, tous les utilisateurs de `main` rapportent la même
    version alors qu'ils exécutent des commits différents. On ne peut pas non
    plus dériver la version du tag (setuptools-scm) : `install.sh` clone en
    `--depth 1`, sans tags, ce qui produirait une version fantaisiste et
    *inférieure* au dernier tag réel. `install.sh` note donc le SHA au moment
    du `pip install`, et on le lit ici. Absent = installé autrement (paquet
    distro, `pip install` direct) : ce n'est pas une erreur.
    """
    try:
        return _revision_file().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _revision_file() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / DISTRIBUTION_NAME / "installed-revision.txt"


def version_line() -> str:
    """« stalker-gamma-linux 0.1.0 (rév. a1b2c3d) » — l'identité exacte du binaire."""
    revision = installed_revision()
    suffix = f" ({_('rev.')} {revision})" if revision else ""
    return f"{DISTRIBUTION_NAME} {package_version()}{suffix}"


def anonymize(text: str, home: Path | None = None) -> str:
    """Remplace le home de l'utilisateur par `~` — le rapport finit sur un ticket public."""
    resolved = str(home if home is not None else Path.home())
    return text.replace(resolved, "~") if resolved not in ("", "/") else text


def _log_tail(lines: int = _LOG_TAIL_LINES) -> str:
    path = logging_setup.log_file()
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _("(no log file at {path})").format(path=path)
    tail = content.splitlines()[-lines:]
    return "\n".join(tail) if tail else _("(log file is empty)")


def _proton_builds() -> str:
    builds = proton.find_proton_builds()
    if not builds:
        return _("(no Proton build found)")
    return "\n".join(f"  - {build.name} ({build.path})" for build in builds)


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}\n"


def build_bundle(report: DoctorReport, *, log_tail: str | None = None) -> str:
    """Assemble le rapport complet en texte brut, prêt à coller dans une issue."""
    header = "\n".join(
        [
            version_line(),
            f"Python {sys.version.split()[0]} — {platform.platform()}",
            f"Target: {report.target}",
        ]
    )
    body = "".join(
        [
            _section(_("Report"), header),
            _section(_("Environment"), format_report(report.environment)),
            _section(_("Proton prefix"), format_prefix_report(report.prefix)),
            _section(_("Proton builds installed"), _proton_builds()),
            _section(_("Installation"), state_module.format_state(report.install, report.target)),
            _section(
                _("GAMMA detected on disk"),
                _("yes") if report.installed_on_disk else _("no"),
            ),
            _section(
                _("Log (last {count} lines)").format(count=_LOG_TAIL_LINES),
                _log_tail() if log_tail is None else log_tail,
            ),
        ]
    )
    return anonymize(body)


def run_report(target: Path | None = None, destination: Path | None = None) -> int:
    """Commande `doctor --report` : écrit le rapport dans un fichier, ou l'affiche."""
    from stalker_gamma_linux import output

    bundle = build_bundle(build_full_report(target))

    if destination is None:
        print(bundle)
        return 0
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(bundle, encoding="utf-8")
    except OSError as error:
        output.error(
            _("Could not write the report to {path}: {error}").format(path=destination, error=error)
        )
        return 1
    output.success(
        _(
            "Diagnostic report written to {path}\n"
            "Attach it to your issue: it contains the prerequisites, the prefix "
            "state and the end of the log. Paths are anonymized (~)."
        ).format(path=destination)
    )
    return 0
