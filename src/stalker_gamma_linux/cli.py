"""Point d'entrée console `stalker-gamma-linux`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from stalker_gamma_linux.environment import run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stalker-gamma-linux",
        description="Installateur et intégration Linux pour S.T.A.L.K.E.R. G.A.M.M.A.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser(
        "doctor", help="Vérifie les prérequis système (distribution, Steam, disque, GPU...)"
    )
    doctor_parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Répertoire d'installation visé (défaut : ~/Games/stalker-gamma)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor(args.target)

    parser.error(f"commande inconnue : {args.command}")
    return 2
