"""Point d'entrée console `stalker-gamma-linux`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import run_doctor
from stalker_gamma_linux.mo2 import run_mo2, run_play
from stalker_gamma_linux.mo2.launch import DEFAULT_EXECUTABLE
from stalker_gamma_linux.orchestrator import run_install
from stalker_gamma_linux.prefix import run_prefix_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stalker-gamma-linux",
        description="Installateur et intégration Linux pour S.T.A.L.K.E.R. G.A.M.M.A.",
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

    doctor_parser = subparsers.add_parser(
        "doctor", help="Vérifie les prérequis système (distribution, Steam, disque, GPU...)"
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        return run_install(args.target)
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

    parser.error(f"commande inconnue : {args.command}")
    return 2
