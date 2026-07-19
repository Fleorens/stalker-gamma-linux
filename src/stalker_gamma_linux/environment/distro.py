"""Détection de la distribution Linux via /etc/os-release."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from stalker_gamma_linux.environment import system

DEFAULT_OS_RELEASE = Path("/etc/os-release")


class DistroFamily(StrEnum):
    FEDORA = "fedora"
    ARCH = "arch"
    DEBIAN = "debian"
    UNKNOWN = "unknown"


_FAMILY_BY_ID = {
    "fedora": DistroFamily.FEDORA,
    "rhel": DistroFamily.FEDORA,
    "centos": DistroFamily.FEDORA,
    "nobara": DistroFamily.FEDORA,
    "arch": DistroFamily.ARCH,
    "manjaro": DistroFamily.ARCH,
    "endeavouros": DistroFamily.ARCH,
    "cachyos": DistroFamily.ARCH,
    "debian": DistroFamily.DEBIAN,
    "ubuntu": DistroFamily.DEBIAN,
    "pop": DistroFamily.DEBIAN,
    "linuxmint": DistroFamily.DEBIAN,
    "steamos": DistroFamily.ARCH,
}


@dataclass(frozen=True, slots=True)
class Distro:
    family: DistroFamily
    pretty_name: str


def parse_os_release(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key] = value.strip().strip('"')
    return values


def detect_family(values: Mapping[str, str]) -> DistroFamily:
    candidates = [values.get("ID", "")]
    candidates.extend(values.get("ID_LIKE", "").split())
    for candidate in candidates:
        family = _FAMILY_BY_ID.get(candidate.lower())
        if family is not None:
            return family
    return DistroFamily.UNKNOWN


def read_os_release(path: Path = DEFAULT_OS_RELEASE) -> dict[str, str]:
    content = system.read_text(path)
    if content is None:
        return {}
    return parse_os_release(content)


def detect_distro(path: Path = DEFAULT_OS_RELEASE) -> Distro:
    values = read_os_release(path)
    return Distro(
        family=detect_family(values),
        pretty_name=values.get("PRETTY_NAME", "distribution inconnue"),
    )
