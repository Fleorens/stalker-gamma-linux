from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.environment.plan import (
    InstallPlan,
    ManualStep,
    build_install_plan,
    format_install_plan,
)


def _report(family: DistroFamily, requirements: list[Requirement]) -> EnvironmentReport:
    return EnvironmentReport(
        distro=Distro(family=family, pretty_name="Test Linux"),
        requirements=tuple(requirements),
    )


def test_groups_blocking_native_packages_into_one_command() -> None:
    report = _report(
        DistroFamily.FEDORA,
        [
            Requirement("Steam", Status.MISSING, "", install_hint="x", key="steam"),
            Requirement("protontricks", Status.MISSING, "", install_hint="x", key="protontricks"),
            Requirement("libunrar", Status.MISSING, "", install_hint="x", key="libunrar"),
            Requirement("7z", Status.OK, "présent", key="7z"),
        ],
    )

    plan = build_install_plan(report, DistroFamily.FEDORA)

    assert plan.package_command == "sudo dnf install steam protontricks unrar"
    assert plan.package_notes == ("dépôt RPM Fusion requis",)
    assert plan.manual_steps == ()


def test_ok_and_unavailable_requirements_are_excluded() -> None:
    report = _report(
        DistroFamily.FEDORA,
        [
            Requirement("Steam", Status.OK, "présent", key="steam"),
            Requirement("GPU Vulkan", Status.UNAVAILABLE, "normal en VM"),
        ],
    )

    assert build_install_plan(report, DistroFamily.FEDORA).is_empty


def test_non_package_remedies_become_manual_steps() -> None:
    report = _report(
        DistroFamily.FEDORA,
        [
            Requirement(
                "umu-launcher",
                Status.MISSING,
                "",
                install_hint="zipapp officiel",
                key="umu-launcher",
            ),
            Requirement("Espace disque", Status.MISSING, "", install_hint="Libérer de l'espace"),
        ],
    )

    plan = build_install_plan(report, DistroFamily.FEDORA)

    assert plan.package_command is None
    assert plan.manual_steps == (
        ManualStep("umu-launcher", "zipapp officiel"),
        ManualStep("Espace disque", "Libérer de l'espace"),
    )


def test_unknown_family_falls_back_to_manual_hints() -> None:
    report = _report(
        DistroFamily.UNKNOWN,
        [Requirement("Steam", Status.MISSING, "", install_hint="flatpak install …", key="steam")],
    )

    plan = build_install_plan(report, DistroFamily.UNKNOWN)

    assert plan.package_command is None
    assert plan.manual_steps == (ManualStep("Steam", "flatpak install …"),)


def test_format_install_plan_renders_single_block() -> None:
    plan = InstallPlan(
        package_command="sudo dnf install steam",
        package_notes=("dépôt RPM Fusion requis",),
        manual_steps=(ManualStep("umu-launcher", "zipapp officiel"),),
    )

    text = "\n".join(format_install_plan(plan))

    assert "Pour tout installer d'un coup :" in text
    assert "sudo dnf install steam" in text
    assert "(dépôt RPM Fusion requis)" in text
    assert "umu-launcher : zipapp officiel" in text


def test_format_empty_plan_is_blank() -> None:
    assert format_install_plan(InstallPlan(None, (), ())) == []
