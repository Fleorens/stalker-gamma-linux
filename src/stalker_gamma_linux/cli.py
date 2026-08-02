"""Point d'entrée console `stalker-gamma-linux`."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux import logging_setup, output, sizing
from stalker_gamma_linux.desktop import run_shortcut
from stalker_gamma_linux.doctor import run_doctor
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2 import run_mo2, run_play
from stalker_gamma_linux.mo2.launch import DEFAULT_EXECUTABLE
from stalker_gamma_linux.orchestrator import CANCELLED_EXIT_CODE, run_install, run_update
from stalker_gamma_linux.prefix import run_prefix_doctor
from stalker_gamma_linux.prefix.umu import run_install_umu
from stalker_gamma_linux.report_bundle import run_report
from stalker_gamma_linux.uninstall import run_uninstall

_logger = logging.getLogger(logging_setup.LOGGER_NAME)

_TARGET_HELP = _("Target install directory (default: ~/Games/stalker-gamma)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stalker-gamma-linux",
        description=_("Linux installer and integration for S.T.A.L.K.E.R. G.A.M.M.A."),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=_(
            "Show details (debug) on the console in addition to the full log "
            "(always written under ~/.local/state/stalker-gamma-linux/)"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser(
        "install",
        help=_(
            "Installs Anomaly + the G.A.M.M.A modpack under --target "
            "(~{total} GiB on disk, {minimum} GiB free required)"
        ).format(total=sizing.TOTAL_INSTALL_GIB, minimum=sizing.MINIMUM_FREE_GIB),
    )
    install_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)
    install_parser.add_argument(
        "--shortcut",
        action="store_true",
        help=_("Also creates the desktop shortcut (.desktop + icon) at the end of the install"),
    )

    update_parser = subparsers.add_parser(
        "update",
        help=_("Updates the G.A.M.M.A modpack, removes ReShade, and re-verifies the install"),
    )
    update_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help=_("Full report: system prerequisites + prefix status + install status"),
    )
    doctor_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)
    doctor_parser.add_argument(
        "--report",
        nargs="?",
        const=Path("stalker-gamma-linux-report.txt"),
        type=Path,
        default=None,
        metavar="FILE",
        help=_(
            "Writes a full diagnostic report to attach to an issue "
            "(prerequisites + prefix + end of log, paths anonymized). "
            "Without a filename: stalker-gamma-linux-report.txt. Use `-` for stdout"
        ),
    )

    prefix_doctor_parser = subparsers.add_parser(
        "prefix-doctor",
        help=_("Checks the shared Proton prefix status (Proton, verbs, DXVK)"),
    )
    prefix_doctor_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)
    prefix_doctor_parser.add_argument(
        "--repair",
        action="store_true",
        help=_("Repairs: downloads Proton-GE, creates the prefix, applies missing verbs"),
    )

    mo2_parser = subparsers.add_parser(
        "mo2", help=_("Opens Mod Organizer 2 (prefix ready, GAMMA instance configured)")
    )
    mo2_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)

    play_parser = subparsers.add_parser(
        "play", help=_("Launches Anomaly through MO2 (USVFS active) and diagnoses the mods")
    )
    play_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)
    play_parser.add_argument(
        "--executable",
        default=DEFAULT_EXECUTABLE,
        help=_("MO2 executable to launch (default: « {executable} »)").format(
            executable=DEFAULT_EXECUTABLE
        ),
    )
    play_parser.add_argument(
        "--flat",
        action="store_true",
        help=_(
            "Fallback without MO2: merged install (usvfs-workaround). "
            "LOSES mod flexibility — only use if USVFS doesn't mount"
        ),
    )
    play_parser.add_argument(
        "--no-diagnose",
        action="store_true",
        help=_("Doesn't run the USVFS diagnostic after launch"),
    )

    shortcut_parser = subparsers.add_parser(
        "shortcut",
        help=_("Creates/updates the desktop shortcut (.desktop + icon, application menu)"),
    )
    shortcut_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help=_("Removes shortcuts, settings, state and logs (keeps the game by default)"),
    )
    uninstall_parser.add_argument("--target", type=Path, default=None, help=_TARGET_HELP)
    uninstall_parser.add_argument(
        "--game-data",
        action="store_true",
        help=_(
            "Also deletes the install directory (Anomaly, mods, cache, Proton "
            "prefix): ~{total} GiB and your saves. Irreversible"
        ).format(total=sizing.TOTAL_INSTALL_GIB),
    )
    uninstall_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=_("Shows exactly what would be removed, without deleting anything"),
    )
    # Contrat interne avec `install.sh --uninstall`, qui retire le venv lui-même
    # juste après nous : sans ça on lui conseillerait de supprimer à la main un
    # répertoire déjà parti. Masqué de l'aide, ce n'est pas un choix utilisateur.
    uninstall_parser.add_argument("--no-venv-hint", action="store_true", help=argparse.SUPPRESS)

    subparsers.add_parser(
        "install-umu",
        help=_(
            "Installs umu-launcher (official zipapp ~420 KiB) into ~/.local/bin — "
            "no sudo, the only prerequisite with no Fedora/Debian package"
        ),
    )

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "install":
        return run_install(args.target, shortcut=args.shortcut)
    if args.command == "update":
        return run_update(args.target)
    if args.command == "doctor":
        if args.report is not None:
            # `-` = sortie standard, pour un `| xclip` ou une redirection.
            destination = None if str(args.report) == "-" else args.report
            return run_report(args.target, destination)
        return run_doctor(args.target)
    if args.command == "prefix-doctor":
        return run_prefix_doctor(args.target, repair=args.repair)
    if args.command == "mo2":
        return run_mo2(args.target)
    if args.command == "play":
        return run_play(
            args.target,
            flat_mode=args.flat,
            executable=args.executable,
            diagnose=not args.no_diagnose,
        )
    if args.command == "shortcut":
        return run_shortcut(args.target)
    if args.command == "install-umu":
        return run_install_umu()
    if args.command == "uninstall":
        return run_uninstall(
            args.target,
            game_data=args.game_data,
            dry_run=args.dry_run,
            venv_hint=not args.no_venv_hint,
        )
    raise AssertionError(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_path = logging_setup.configure_logging(verbose=args.verbose)

    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        # Ctrl-C est un usage **documenté** (README : interrompre puis relancer,
        # les étapes validées sont sautées). Sans ce handler, l'utilisateur qui
        # le fait au milieu d'un `full-install` reçoit une traceback brute :
        # `KeyboardInterrupt` est une `BaseException`, donc jamais attrapée
        # ci-dessous. Même code de sortie et même message que l'annulation GUI.
        _logger.info("`%s` interrupted by the user (Ctrl-C)", args.command)
        output.warn(
            _("\nInterrupted. Steps already validated are kept — rerun the same command to resume.")
        )
        return CANCELLED_EXIT_CODE
    except Exception:
        _logger.exception("unexpected error during `%s`", args.command)
        output.error(
            _("unexpected error — see the log for details."),
            hint=_(
                "Check {log_path} (or retry with --verbose) and open an "
                "issue if the problem persists."
            ).format(log_path=log_path),
        )
        return 1
