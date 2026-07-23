# stalker-gamma-linux

[![CI](https://github.com/Fleorens/stalker-gamma-linux/actions/workflows/ci.yml/badge.svg)](https://github.com/Fleorens/stalker-gamma-linux/actions/workflows/ci.yml)

**A real Linux port of the [S.T.A.L.K.E.R. G.A.M.M.A.](https://github.com/Grokitach/Stalker_GAMMA) installation experience.**

The game itself (Anomaly, X-Ray Monolith engine) already runs great under Proton.
What does *not* work on Linux is everything around it: the official launcher is
.NET + PowerShell, Mod Organizer 2 needs careful Wine/Proton setup, and today's
community guides require a dozen manual steps.

This project is the **Linux integration layer** that makes GAMMA a one-command
(and eventually one-click) install:

- One-shot installer: prerequisites check → Anomaly → GAMMA modpack → Proton prefix → desktop shortcut
- **Mod Organizer 2 running under Proton as the primary mode** — you keep full
  mod flexibility (enable/disable/add mods), exactly like on Windows
- Incremental updates that follow upstream GAMMA releases
- Works on any Linux distribution — desktop (Fedora, Arch, Debian/Ubuntu, …) as well as Steam Deck
- GUI on top (GTK4/libadwaita); packaged as a Flatpak (primary, GUI + CLI)
  and an AppImage (portable CLI) — see [docs/PACKAGING.md](docs/PACKAGING.md)

## How it works

We do **not** reimplement the modpack installation logic. The download/install
engine is [Mord3rca/gamma-launcher](https://github.com/Mord3rca/gamma-launcher)
(Python, GPL-3.0), which already handles ModDB mirror resolution, the GAMMA
modlist, extraction directives and MD5 verification. This project wraps it with
everything Linux-specific. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

🚧 Phase 1 (MVP) implemented and validated on a real machine; the GTK4/
libadwaita GUI (Phase 2) is implemented and tested on a real machine too;
Flatpak + AppImage packaging (Phase 3) builds and runs locally; CI (lint,
types, tests, packaging release, daily upstream-regression watch) is wired
up — see [docs/ROADMAP.md](docs/ROADMAP.md), [docs/CI.md](docs/CI.md) and
[tasks/](tasks/) for the work breakdown.

## Usage

### Install

Three ways to get the CLI/GUI running — pick whichever fits your setup, they
all end up at the same `install`/`play`/`doctor` commands.

**Flatpak** (recommended — sandboxed, includes the GUI, works on Steam Deck):
see [docs/PACKAGING.md](docs/PACKAGING.md) to build it locally with
`make package-flatpak` (not yet on Flathub — a submission is staged but not
sent, see `packaging/flatpak/flathub/`).

**AppImage** (portable, CLI only): `make package-appimage`, then run the
produced `packaging/appimage/dist/stalker-gamma-linux-*.AppImage` directly —
see [docs/PACKAGING.md](docs/PACKAGING.md).

**From source / curl script**:

The Flatpak/AppImage channels above bundle everything they need. This path
doesn't: the one hard prerequisite is **umu-launcher** (`umu-run` in your
`PATH`) — once it's there, Proton-GE, the Wine prefix, winetricks verbs and
DXVK are all downloaded/configured automatically, no `sudo` involved. No
native package on Fedora/Debian/Ubuntu yet: `pipx install umu-launcher`, or
the official
["zipapp" release](https://github.com/Open-Wine-Components/umu-launcher/releases)
symlinked into `~/.local/bin`. On Arch: `sudo pacman -S umu-launcher`. Steam,
protontricks, `7z`, `libunrar` and Vulkan drivers help but are secondary —
`install.sh` below runs `doctor` first and warns if any of this is missing,
*before* it commits to the ~90 GB download.

```sh
curl -fsSL https://raw.githubusercontent.com/Fleorens/stalker-gamma-linux/main/install.sh | bash
```

This bootstraps a venv under `~/.local/share/stalker-gamma-linux/` (no
`sudo`), installs the package, links `~/.local/bin/stalker-gamma-linux`, and
runs `install`. Already have a checkout? `./install.sh` does the same without
cloning. Either form forwards extra arguments to `install`, e.g.
`./install.sh --target /mnt/games --shortcut`.

Once installed (or with the venv activated), the CLI is `stalker-gamma-linux`:

```sh
stalker-gamma-linux doctor                       # system prerequisites + prefix + install state
stalker-gamma-linux install                      # anomaly → GAMMA → prefix → MO2 → (default target: ~/Games/stalker-gamma)
stalker-gamma-linux install --target /mnt/disk --shortcut   # custom disk, + desktop entry
stalker-gamma-linux play                         # launch Anomaly through MO2 (USVFS, mods active)
stalker-gamma-linux mo2                          # open Mod Organizer 2 itself (enable/disable mods)
stalker-gamma-linux update                       # update the modpack, re-verify, remove ReShade again if needed
stalker-gamma-linux shortcut                     # (re)create the .desktop menu entry
stalker-gamma-linux prefix-doctor --repair        # repair the shared Proton prefix in place
```

Every command has `--help`. `install` is resumable: interrupt it (Ctrl-C) and
rerun the same command — steps already completed (tracked in
`~/.config/stalker-gamma-linux/install-state.toml`) are skipped. Pass
`--verbose` (before the subcommand, e.g. `stalker-gamma-linux --verbose play`)
for debug output on the console; a full rotating log is always kept under
`~/.local/state/stalker-gamma-linux/`.

### GUI

A GTK4/libadwaita GUI is available as `stalker-gamma-linux-gui` — install →
play without touching a terminal, plus a graphical Diagnostic view and a
Preferences window (install path, Proton-GE version, desktop-shortcut
opt-in). It needs GTK4 + libadwaita + PyGObject from your distribution (not
pip-installable — no manylinux wheel exists for PyGObject); running the
command without them prints the install command for your distro instead of
a raw traceback. It calls the exact same `orchestrator`/`mo2` code as the
CLI — no duplicated install logic — and never blocks the UI thread during a
download. The CLI remains fully independent and usable on its own.

## Legal

This repository contains **code and documentation only**. It never rehosts the
game, Anomaly, or any mod: everything is downloaded client-side from ModDB /
GitHub, exactly like the official GAMMA launcher does. All credit for GAMMA
goes to Grokitach and the modders listed at [stalker-gamma.com](https://stalker-gamma.com).

License: [GPL-3.0](LICENSE).
