"""État de santé du préfixe partagé et réparation (commande `prefix-doctor`)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.models import Requirement, Status
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix import proton, provision, verbs
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_REPAIR_HINT = "stalker-gamma-linux prefix-doctor --repair"

_STATUS_LABEL = {
    Status.OK: _("[ OK ]"),
    Status.MISSING: _("[MISSING]"),
    Status.OUTDATED: _("[OUTDATED]"),
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
        return Requirement(name="umu-launcher", status=Status.OK, detail=_("umu-run detected"))
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail=_("umu-run not found in PATH"),
        install_hint=_(
            "Install umu-launcher (see `stalker-gamma-linux doctor`); "
            "manual fallback: protontricks, docs/INSTALL-MANUAL.md §6.1-6.2"
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
        detail=_(
            "no Proton build (neither GE in compatibilitytools.d, "
            "nor Steam's Proton Experimental)"
        ),
        install_hint=_(
            "`{hint}` downloads the latest GE-Proton release (checksum verified)"
        ).format(hint=_REPAIR_HINT),
    )


def _check_prefix(paths: PrefixPaths) -> Requirement:
    if not provision.is_initialized(paths):
        return Requirement(
            name=_("Prefix"),
            status=Status.MISSING,
            detail=_("not initialized ({path} has no system.reg)").format(path=paths.prefix),
            install_hint=_REPAIR_HINT,
        )
    version = system.read_text(paths.version_file)
    detail = _("initialized")
    if version is not None and version.strip():
        detail += _(" (prefix Proton: {version})").format(
            version=version.strip().splitlines()[0]
        )
    return Requirement(name=_("Prefix"), status=Status.OK, detail=detail)


def _check_verbs(paths: PrefixPaths) -> Requirement:
    missing = verbs.missing_verbs(paths)
    total = len(verbs.REQUIRED_VERBS)
    if not missing:
        return Requirement(
            name=_("Winetricks verbs"),
            status=Status.OK,
            detail=_("{total}/{total} present").format(total=total),
        )
    return Requirement(
        name=_("Winetricks verbs"),
        status=Status.MISSING,
        detail=_("{done}/{total} present — missing: {missing}").format(
            done=total - len(missing), total=total, missing=", ".join(missing)
        ),
        install_hint=_REPAIR_HINT,
    )


def _check_dxvk(paths: PrefixPaths) -> Requirement:
    if not provision.is_initialized(paths):
        return Requirement(
            name="DXVK",
            status=Status.MISSING,
            detail=_("prefix not initialized"),
            install_hint=_REPAIR_HINT,
        )
    for dll in _DXVK_DLLS:
        try:
            data = (paths.system32 / dll).read_bytes()
        except OSError:
            continue
        if b"DXVK" in data:
            return Requirement(
                name="DXVK", status=Status.OK, detail=_("{dll} provided by DXVK").format(dll=dll)
            )
    return Requirement(
        name="DXVK",
        status=Status.MISSING,
        detail=_("no DXVK DLL ({dlls}) detected in system32").format(
            dlls="/".join(_DXVK_DLLS)
        ),
        install_hint=_(
            "Proton bundles DXVK — never install the winetricks verb `dxvk` "
            "(docs/INSTALL-MANUAL.md §6.2). Retry `{hint}`; if the problem "
            "persists, check the Proton version."
        ).format(hint=_REPAIR_HINT),
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
        lines.append(_("The prefix is healthy."))
    else:
        lines.append(_("The prefix needs repairing (--repair)."))
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
            print(_("\nRepair failed: {error}").format(error=error))
            return 1
        report = build_prefix_report(paths, search_dirs)

    print(format_prefix_report(report))
    return 0 if report.is_healthy else 1
