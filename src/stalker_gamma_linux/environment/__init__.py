"""Détection des prérequis système (distribution, Steam, Proton, disque, GPU)."""

from stalker_gamma_linux.environment.distro import Distro, DistroFamily, detect_distro
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.environment.plan import (
    InstallPlan,
    ManualStep,
    build_install_plan,
    format_install_plan,
)
from stalker_gamma_linux.environment.report import build_report, format_report, run_doctor

__all__ = [
    "Distro",
    "DistroFamily",
    "EnvironmentReport",
    "InstallPlan",
    "ManualStep",
    "Requirement",
    "Status",
    "build_install_plan",
    "build_report",
    "detect_distro",
    "format_install_plan",
    "format_report",
    "run_doctor",
]
