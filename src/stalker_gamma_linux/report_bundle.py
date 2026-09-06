"""Rapport de diagnostic exportable (`doctor --report`), à joindre à une issue.

Sans ça, un utilisateur qui signale un problème doit copier-coller à la main la
sortie de `doctor`, retrouver le journal sous `~/.local/state/`, et penser à
préciser sa version et son build Proton — donc en pratique il n'envoie qu'un
tiers de ce qu'il faut, et chaque issue coûte deux ou trois allers-retours.

Ce module ne collecte rien de nouveau : `doctor.build_full_report` sépare déjà
la collecte du rendu, on ne fait que l'assembler avec la version du paquet, la
plate-forme et la fin du journal.

**Anonymisation** : le home est réécrit en `~/…`, ainsi que `/run/user/<uid>`
et le nom de compte nu partout où il traîne encore — cible d'installation hors
du home, `/media/<user>/…`, journaux Proton/umu inclus dans le rapport. Sans
ça, le nom de compte apparaît des dizaines de fois dans un rapport destiné à un
ticket public. Ce n'est pas un anonymat fort — c'est le minimum décent quand on
demande à quelqu'un de coller un fichier sur GitHub. Voir `anonymize()` pour
les garde-fous contre les faux positifs sur les noms de compte courts.
"""

from __future__ import annotations

import os
import platform
import re
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


# Un nom de compte de 1 ou 2 caractères est trop dangereux à réécrire en aveugle :
# il a de bonnes chances d'apparaître comme fragment d'autre chose (un compte
# « ge » écraserait « GE-Proton11-1 »). En dessous de ce seuil, on préfère
# laisser fuiter le nom de compte plutôt que de mutiler le reste du rapport.
_MIN_ANONYMIZED_USER_LENGTH = 3


def anonymize(
    text: str,
    home: Path | None = None,
    user: str | None = None,
    uid: int | None = None,
) -> str:
    """Réécrit en `~` tout ce qui identifie l'utilisateur : home, uid, nom de compte.

    Trois remplacements, appliqués dans cet ordre précis :
    1. le home complet (`/home/marie` → `~`) — la chaîne la plus longue et la
       plus spécifique, donc celle qu'on préfère faire correspondre en premier ;
    2. `/run/user/<uid>` — le `XDG_RUNTIME_DIR` de Proton/umu, indépendant du
       home ;
    3. le nom de compte nu, partout où il traîne encore : cible d'installation
       hors du home, `/media/<user>/…`, chemins Proton dans le journal.

    Le nom de compte nu est le remplacement le plus risqué des trois : contrairement
    au home ou à l'uid (des chemins complets, peu susceptibles d'apparaître par
    hasard), c'est une chaîne courte qui peut coïncider avec un fragment d'autre
    chose dans le rapport. Deux garde-fous, combinés :
    - une longueur minimale (`_MIN_ANONYMIZED_USER_LENGTH`) : sous ce seuil, pas
      de remplacement du tout, plutôt que de risquer de la casse ;
    - des frontières de mot (`\\b`) : le nom de compte n'est réécrit que là où il
      n'est pas collé à d'autres lettres ou chiffres (ça protège par exemple
      "banana" d'un compte "ana").
    Ce n'est pas parfait : un compte de 3+ caractères séparé d'un autre mot par un
    tiret ou un underscore (les deux sont des séparateurs de mot pour `\\b` autant
    que des séparateurs de composants de version) reste vulnérable — c'est un
    compromis assumé, pas un trou qu'on a raté.
    """
    home_path = home if home is not None else Path.home()
    resolved_home = str(home_path)
    result = text.replace(resolved_home, "~") if resolved_home not in ("", "/") else text

    resolved_uid = os.getuid() if uid is None else uid
    result = re.sub(rf"/run/user/{resolved_uid}\b", "/run/user/~", result)

    resolved_user = (
        user
        if user is not None
        else (os.environ.get("USER") or os.environ.get("LOGNAME") or home_path.name or None)
    )
    if resolved_user and len(resolved_user) >= _MIN_ANONYMIZED_USER_LENGTH:
        result = re.sub(rf"\b{re.escape(resolved_user)}\b", "~", result)

    return result


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
