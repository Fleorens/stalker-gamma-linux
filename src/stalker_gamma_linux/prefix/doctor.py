"""État de santé du préfixe partagé et réparation (commande `prefix-doctor`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.models import Requirement, Status
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.prefix import proton, provision, verbs
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_REPAIR_HINT = "stalker-gamma-linux prefix-doctor --repair"

_STATUS_LABEL = {
    Status.OK: "[ OK ]",
    Status.MISSING: "[MANQUANT]",
    Status.OUTDATED: "[ANCIEN]",
}

# DLL que Proton remplace par les builds DXVK ; celles-ci contiennent la
# chaîne « DXVK » dans le binaire, contrairement aux builtin Wine.
_DXVK_DLLS = ("d3d11.dll", "dxgi.dll")


@dataclass(frozen=True, slots=True)
class PrefixReport:
    requirements: tuple[Requirement, ...]

    @property
    def is_healthy(self) -> bool:
        return all(requirement.status is Status.OK for requirement in self.requirements)


def _check_umu() -> Requirement:
    if system.which("umu-run") is not None:
        return Requirement(name="umu-launcher", status=Status.OK, detail="umu-run détecté")
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail="umu-run introuvable dans le PATH",
        install_hint=(
            "Installe umu-launcher (voir `stalker-gamma-linux doctor`) ; "
            "fallback manuel : protontricks, docs/INSTALL-MANUAL.md §6.1-6.2"
        ),
    )


def _check_proton(build: proton.ProtonBuild | None) -> Requirement:
    if build is not None:
        return Requirement(
            name="Proton", status=Status.OK, detail=f"{build.name} ({build.path})"
        )
    return Requirement(
        name="Proton",
        status=Status.MISSING,
        detail=(
            "aucun build Proton (ni GE dans compatibilitytools.d, "
            "ni Proton Experimental de Steam)"
        ),
        install_hint=(
            f"`{_REPAIR_HINT}` télécharge la dernière release GE-Proton (checksum vérifié)"
        ),
    )


def _check_prefix(paths: PrefixPaths) -> Requirement:
    if not provision.is_initialized(paths):
        return Requirement(
            name="Préfixe",
            status=Status.MISSING,
            detail=f"non initialisé ({paths.prefix} sans system.reg)",
            install_hint=_REPAIR_HINT,
        )
    version = system.read_text(paths.version_file)
    detail = "initialisé"
    if version is not None and version.strip():
        detail += f" (Proton du préfixe : {version.strip().splitlines()[0]})"
    return Requirement(name="Préfixe", status=Status.OK, detail=detail)


def _check_verbs(paths: PrefixPaths) -> Requirement:
    missing = verbs.missing_verbs(paths)
    total = len(verbs.REQUIRED_VERBS)
    if not missing:
        return Requirement(
            name="Verbs winetricks", status=Status.OK, detail=f"{total}/{total} présents"
        )
    return Requirement(
        name="Verbs winetricks",
        status=Status.MISSING,
        detail=f"{total - len(missing)}/{total} présents — manquants : {', '.join(missing)}",
        install_hint=_REPAIR_HINT,
    )


def _check_dxvk(paths: PrefixPaths) -> Requirement:
    if not provision.is_initialized(paths):
        return Requirement(
            name="DXVK",
            status=Status.MISSING,
            detail="préfixe non initialisé",
            install_hint=_REPAIR_HINT,
        )
    for dll in _DXVK_DLLS:
        try:
            data = (paths.system32 / dll).read_bytes()
        except OSError:
            continue
        if b"DXVK" in data:
            return Requirement(name="DXVK", status=Status.OK, detail=f"{dll} fournie par DXVK")
    return Requirement(
        name="DXVK",
        status=Status.MISSING,
        detail=f"aucune DLL DXVK ({'/'.join(_DXVK_DLLS)}) détectée dans system32",
        install_hint=(
            "Proton embarque DXVK — ne jamais installer le verb winetricks `dxvk` "
            f"(docs/INSTALL-MANUAL.md §6.2). Relance `{_REPAIR_HINT}` ; si le problème "
            "persiste, vérifie la version de Proton."
        ),
    )


def build_prefix_report(
    paths: PrefixPaths, search_dirs: Sequence[Path] | None = None
) -> PrefixReport:
    build = proton.select_proton_build(proton.find_proton_builds(search_dirs))
    return PrefixReport(
        requirements=(
            _check_umu(),
            _check_proton(build),
            _check_prefix(paths),
            _check_verbs(paths),
            _check_dxvk(paths),
        )
    )


def format_prefix_report(report: PrefixReport) -> str:
    lines = []
    for requirement in report.requirements:
        label = _STATUS_LABEL[requirement.status]
        lines.append(f"{label} {requirement.name} — {requirement.detail}")
        if requirement.status is not Status.OK and requirement.install_hint is not None:
            lines.append(f"           → {requirement.install_hint}")
    lines.append("")
    if report.is_healthy:
        lines.append("Le préfixe est sain.")
    else:
        lines.append("Le préfixe nécessite une réparation (--repair).")
    return "\n".join(lines)


def run_prefix_doctor(
    target: Path | None = None,
    *,
    repair: bool = False,
    search_dirs: Sequence[Path] | None = None,
) -> int:
    """Vérifie l'état du préfixe partagé ; avec `repair`, le remet à l'état nominal.

    Réparer = rejouer le provisioning idempotent : seuls le Proton, la création
    du préfixe ou les verbs réellement manquants sont refaits.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    paths = PrefixPaths.under(root)
    report = build_prefix_report(paths, search_dirs)

    if repair and not report.is_healthy:
        try:
            provision.ensure_prefix(paths, search_dirs=search_dirs, on_progress=print)
        except PrefixError as error:
            print(format_prefix_report(report))
            print(f"\nRéparation échouée : {error}")
            return 1
        report = build_prefix_report(paths, search_dirs)

    print(format_prefix_report(report))
    return 0 if report.is_healthy else 1
