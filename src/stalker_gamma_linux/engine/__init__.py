"""Wrapper autour du moteur gamma-launcher (téléchargement/installation GAMMA)."""

from stalker_gamma_linux.engine.errors import (
    EngineCancelledError,
    EngineError,
    EngineExecutionError,
    EngineNotFoundError,
    VerificationError,
)
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.engine.process import ProgressCallback
from stalker_gamma_linux.engine.runner import (
    build_flat_install,
    install_anomaly,
    install_gamma,
    purge_shader_cache,
    remove_reshade,
    update_gamma,
    verify,
)

__all__ = [
    "EngineCancelledError",
    "EngineError",
    "EngineExecutionError",
    "EngineNotFoundError",
    "InstallPaths",
    "ProgressCallback",
    "VerificationError",
    "build_flat_install",
    "install_anomaly",
    "install_gamma",
    "purge_shader_cache",
    "remove_reshade",
    "update_gamma",
    "verify",
]
