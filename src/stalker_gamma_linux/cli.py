"""Point d'entrée console `stalker-gamma-linux`."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux import logging_setup, output
from stalker_gamma_linux.desktop import run_shortcut
from stalker_gamma_linux.doctor import run_doctor
from stalker_gamma_linux.mo2 import run_mo2, run_play
from stalker_gamma_linux.mo2.launch import DEFAULT_EXECUTABLE
from stalker_gamma_linux.orchestrator import run_install, run_update
from stalker_gamma_linux.prefix import run_prefix_doctor

_logger = logging.getLogger(logging_setup.LOGGER_NAME)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stalker-gamma-linux",
        description="Installateur et intégration Linux pour S.T.A.L.K.E.R. G.A.M.M.A.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help=(
            "Affiche le détail (debug) sur la console en plus du journal complet "
            "(toujours écrit dans ~/.local/state/stalker-gamma-linux/)"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser(
        "install",
        help="Installe Anomaly + le modpack G.A.M.M.A sous --target (télécharge ~146 Go)",
    )
    install_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire (et donc disque) d'installation (défaut : ~/Games/stalker-gamma)",
    )
    install_parser.add_argument(
        "--shortcut",
        action="store_true",
        help="Crée aussi le raccourci bureau (.desktop + icône) à la fin de l'installation",
    )

    update_parser = subparsers.add_parser(
        "update",
        help="Met à jour le modpack G.A.M.M.A, retire ReShade et re-vérifie l'installation",
    )
    update_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Rapport complet : prérequis système + état du préfixe + état de l'installation",
    )
    doctor_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )

    prefix_doctor_parser = subparsers.add_parser(
        "prefix-doctor",
        help="Vérifie l'état du préfixe Proton partagé (Proton, verbs, DXVK)",
    )
    prefix_doctor_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )
    prefix_doctor_parser.add_argument(
        "--repair",
        action="store_true",
        help="Répare : télécharge Proton-GE, crée le préfixe, applique les verbs manquants",
    )

    mo2_parser = subparsers.add_parser(
        "mo2", help="Ouvre Mod Organizer 2 (préfixe prêt, instance GAMMA configurée)"
    )
    mo2_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )

    play_parser = subparsers.add_parser(
        "play", help="Lance Anomaly à travers MO2 (USVFS actif) et diagnostique les mods"
    )
    play_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )
    play_parser.add_argument(
        "--executable",
        default=DEFAULT_EXECUTABLE,
        help=f"Exécutable MO2 à lancer (défaut : « {DEFAULT_EXECUTABLE} »)",
    )
    play_parser.add_argument(
        "--flat",
        action="store_true",
        help=(
            "Fallback sans MO2 : installation fusionnée (usvfs-workaround). "
            "PERTE de la flexibilité des mods — à n'utiliser que si l'USVFS ne monte pas"
        ),
    )
    play_parser.add_argument(
        "--no-diagnose",
        action="store_true",
        help="N'exécute pas le diagnostic USVFS après le lancement",
    )

    shortcut_parser = subparsers.add_parser(
        "shortcut",
        help="Crée/actualise le raccourci bureau (.desktop + icône, menu applications)",
    )
    shortcut_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "install":
        return run_install(args.target, shortcut=args.shortcut)
    if args.command == "update":
        return run_update(args.target)
    if args.command == "doctor":
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
    raise AssertionError(f"commande inconnue : {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_path = logging_setup.configure_logging(verbose=args.verbose)

    try:
        return _dispatch(args)
    except Exception:
        _logger.exception("erreur inattendue pendant `%s`", args.command)
        output.error(
            "erreur inattendue — détail dans le journal.",
            hint=(
                f"Consulte {log_path} (ou relance avec --verbose) et ouvre une "
                "issue si le problème persiste."
            ),
        )
        return 1
