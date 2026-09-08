# stalker-gamma-linux

[![CI](https://github.com/Fleorens/stalker-gamma-linux/actions/workflows/ci.yml/badge.svg)](https://github.com/Fleorens/stalker-gamma-linux/actions/workflows/ci.yml)

**Install [S.T.A.L.K.E.R. G.A.M.M.A.](https://github.com/Grokitach/Stalker_GAMMA)
on Linux with one command** — Mod Organizer 2 under Proton, your mods still
enable/disable like on Windows.

![Accueil du launcher](docs/screenshots/accueil.png)

The game itself (Anomaly, X-Ray Monolith engine) already runs great under Proton.
Everything *around* it is the problem: the official launcher is .NET + PowerShell,
Mod Organizer 2 needs a careful Wine/Proton setup, and the community route is a
long manual checklist. Same install, before and after:

| By hand ([INSTALL-MANUAL.md](docs/INSTALL-MANUAL.md), the spec this project automates) | With this project |
|---|---|
| 8 documented steps, plus a page of known traps | `curl … \| bash`, then one window |
| ≈ 160 GiB of downloads to shepherd yourself | Progress, disk check and resume built in |
| Official launcher: .NET + PowerShell, Windows-only | Native GTK4/libadwaita launcher |
| Proton prefix, DLL injection, winetricks verbs by hand | Shared prefix provisioned — and repairable (`prefix-doctor --repair`) |
| MO2 `gamePath` and profile edited by hand in `ModOrganizer.ini` | Configured for you, USVFS diagnosed after launch |
| Interrupted mid-way? Start over | Resumable: rerun, completed steps are skipped |
| "works on my distro" | Exercised in CI on Fedora, Arch, Debian 12 and Ubuntu 24.04 on every push |

This project is the **Linux integration layer** that makes GAMMA a one-command
(and eventually one-click) install:

- One-shot installer: prerequisites check → Anomaly → GAMMA modpack → Proton prefix → desktop shortcut
- **Mod Organizer 2 running under Proton as the primary mode** — you keep full
  mod flexibility (enable/disable/add mods), exactly like on Windows
- Incremental updates that follow upstream GAMMA releases
- Runs on any Linux distribution — the installer is exercised in CI on **Fedora,
  Arch, Debian 12 and Ubuntu 24.04** containers on every push; other distros are
  expected to work but aren't tested automatically. Steam Deck included.
- GUI on top (GTK4/libadwaita), installed natively (no Flatpak/AppImage sandbox)

## How it works

We do **not** reimplement the modpack installation logic. The download/install
engine is [Mord3rca/gamma-launcher](https://github.com/Mord3rca/gamma-launcher)
(Python, GPL-3.0), which already handles ModDB mirror resolution, the GAMMA
modlist, extraction directives and MD5 verification. This project wraps it with
everything Linux-specific. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

🚧 Phase 1 (MVP) implemented and validated on a real machine; the GTK4/
libadwaita GUI (Phase 2) is implemented and tested on a real machine too;
install is native only (`install.sh`, no Flatpak/AppImage); CI (lint, types,
tests, release tagging, daily upstream-regression watch) is wired up — see
[docs/ROADMAP.md](docs/ROADMAP.md), [docs/CI.md](docs/CI.md) and
[tasks/](tasks/) for the work breakdown.

## Usage

### Install

The recommended install is **one command** that sets up a native environment
and **opens the installer GUI** — the actual installation experience:

```sh
curl -fsSL https://raw.githubusercontent.com/Fleorens/stalker-gamma-linux/main/install.sh | bash
```

No `sudo`, nothing written outside your home. It bootstraps a
`--system-site-packages` venv under `~/.local/share/stalker-gamma-linux/`,
installs the package, adds a **GAMMA Linux Launcher** entry to your app menu,
and launches the GUI. The window drives the rest: live prerequisite diagnostic,
install target, download/install, then Play. Already have a checkout?
`./install.sh` does the same without cloning; `--no-launch` sets everything up
without opening the window.

### Uninstall

```sh
~/.local/share/stalker-gamma-linux/src/install.sh --uninstall   # or ./install.sh --uninstall from a checkout
```

Removes the venv, both commands, the menu entry, the icon, your settings and
the logs. **Your game install is never touched** — the script tells you where
it is so you can delete it yourself. To remove it too, in one step:

```sh
stalker-gamma-linux uninstall --game-data    # irreversible: Anomaly, mods, cache, prefix and saves
stalker-gamma-linux uninstall --dry-run      # shows exactly what would go, deletes nothing
```

`--game-data` asks for an explicit `yes` before deleting (the resolved path
and estimated size are shown first); add `--yes` to skip the prompt in
scripts.

`umu-run` is deliberately left in place: it is a general-purpose launcher that
other games may rely on.

Running **natively** (not sandboxed) is deliberate: this tool orchestrates your
system's Wine/Proton, umu, libunrar, Steam and 32-bit stack — the native GUI
uses them directly, with none of the bundling/sandbox workarounds a Wine
launcher would need in a container.

**Prerequisites** (the GUI's Diagnostic tab shows them live):
- **GTK4 + libadwaita 1.5+ + PyGObject** — for the GUI itself, the one thing the
  script can't set up without `sudo` (PyGObject has no pip wheel; it comes from
  your distro). **Debian 12 ships libadwaita 1.2 and cannot run the graphical
  launcher** — the CLI works fine there; the GUI needs Debian 13, Ubuntu 24.04+,
  Fedora or Arch. `doctor` tells you which case you're in. Fedora: `sudo dnf install gtk4 libadwaita python3-gobject` ·
  Debian/Ubuntu: `sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi` ·
  Arch: `sudo pacman -S gtk4 libadwaita python-gobject`. If they're missing the
  script prints the exact command for your distro.
- **umu-launcher** — **installed automatically**, nothing to do. It is the
  one prerequisite with no PyPI package (`pipx install umu-launcher` 404s)
  and no package in the Fedora/Debian/Ubuntu repos, so the tool handles it
  itself: `install.sh` (and the **Install** button in the GUI's Diagnostic
  view, and `stalker-gamma-linux install-umu`) downloads the official
  ~420 KiB [zipapp release](https://github.com/Open-Wine-Components/umu-launcher/releases)
  and drops `umu-run` into `~/.local/bin` — no sudo. Prefer a real package?
  Arch: `sudo pacman -S umu-launcher`; Fedora/Debian: upstream publishes
  `.rpm`/`.deb` files on the same releases page.
- `7z` and `libunrar` are needed for the install itself (shown in the
  Diagnostic with the exact command for your distro). Steam, protontricks
  and Vulkan drivers are **optional**: the pipeline runs everything through
  umu (own runtime, Proton-GE fetched from GitHub) — Steam only matters for
  Steam Input / Gaming Mode on the Deck, Vulkan only to actually play.
- [**GameMode**](https://github.com/FeralInteractive/gamemode) is optional too,
  and used automatically when present: `play` wraps the launch in
  `gamemoderun`, which is what actually *requests* the mode (the daemon is
  D-Bus-activated, so `gamemoded -s` saying « inactive » between sessions is
  normal, not a bug to fix with `systemctl enable`). Opt out with
  `play --no-gamemode` or the switch in the GUI's Preferences. On Fedora and
  Arch the CPU-governor part is reserved to members of the `gamemode` group by
  a polkit rule, and fails silently otherwise — `doctor` detects that and gives
  you the one-time `usermod` command (effective on the next launch: polkit reads
  the group from the system database, so no re-login needed).
- **MangoHud, gamescope/FSR and vkBasalt** are optional as well, and — unlike
  GameMode — **stay off until you ask for them**: they change how the game
  renders, and « nothing enabled » has to be something you can say in an issue
  without checking. `doctor` lists all three with the install command for your
  distro; the GUI's Preferences and `play` flags turn them on:
  `play --gamescope --gamescope-render 1024x640 --gamescope-output 1280x800`
  renders low and scales up with FSR (the lever Windows does not have — the one
  that makes GAMMA playable on a Steam Deck, where those two resolutions are the
  defaults), `play --mangohud` shows the FPS/frametime overlay
  (`--mangohud-preset full` adds CPU/GPU/VRAM and temperatures), and
  `play --vkbasalt` enables **our « ReShade-like » preset** — CAS sharpening
  plus a bit of colour grading, shipped as a LUT we generate. That last one is
  the concrete answer to the ReShade this installer removes (it is incompatible
  with DXVK). None of them touches your global `MangoHud.conf` or
  `vkBasalt.conf`: we write our own files under
  `~/.config/stalker-gamma-linux/`.

Once installed (or with the venv activated), the CLI is `stalker-gamma-linux`:

```sh
stalker-gamma-linux doctor                       # system prerequisites + prefix + install state
stalker-gamma-linux install                      # anomaly → GAMMA → prefix → MO2 → (default target: ~/Games/stalker-gamma)
stalker-gamma-linux install --target /mnt/disk --shortcut   # custom disk, + desktop entry
stalker-gamma-linux import /path/to/existing     # adopt an install already on disk — no re-download
stalker-gamma-linux play                         # launch Anomaly through MO2 (USVFS, mods active, GameMode if installed)
stalker-gamma-linux play --gamescope --mangohud  # + FSR upscaling and the FPS overlay (both off unless asked)
stalker-gamma-linux mo2                          # open Mod Organizer 2 itself (enable/disable mods)
stalker-gamma-linux postmortem                   # after closing the game: how the last session ended, and which mods to suspect
stalker-gamma-linux update                       # update the modpack, re-verify, keep your mod list
stalker-gamma-linux backup                       # back up profiles + saved games + overwrite (kept, never rotated)
stalker-gamma-linux backup --list                # what you can go back to (date, contents, size)
stalker-gamma-linux restore <id>                 # put one back (the current state is saved first)
stalker-gamma-linux shortcut                     # (re)create the .desktop menu entry
stalker-gamma-linux install --only prefix        # replay one step (troubleshooting), even if done
stalker-gamma-linux verify                       # check the installed mods against their reference fingerprint
stalker-gamma-linux verify --repair              # + reinstall the damaged modpack mods (yours are never touched)
stalker-gamma-linux prefix-doctor --repair        # repair the shared Proton prefix in place
stalker-gamma-linux uninstall                    # remove shortcuts/settings/logs (keeps the game)
stalker-gamma-linux doctor --report              # write a report to attach to an issue
```

**Your mod list survives updates.** On Windows, `Install / Update GAMMA` resets
your modlist, your load order and the mods you added — the official wiki says so
itself, and tells you to make backups first. Here, `update` does three things
instead: it backs up your MO2 profiles **and your saved games** to
`<target>/backups/` before touching anything, it lets the engine write the new
upstream list, then it **replays your own changes on top** and tells you what it
put back ("3 mods re-enabled/disabled the way you had them, 2 mods you added put
back in place, 1 entry removed upstream not restored").

Mods removed upstream are never resurrected (their folder is gone; MO2 would
show them as missing), and when your reordering and the upstream one genuinely
conflict, the upstream order wins and the report says so — a silently wrong
merge is worse than a manual restore. Use `update --no-merge` for the old
behaviour (upstream overwrites, backup still written).

The first update after installing this version has no reference to compare
against yet: it records one, says so, and merges from the next update on.

**Went too far?** `stalker-gamma-linux backup --list` shows every restore point
(five automatic ones are kept, plus every backup you created yourself — those
are never rotated away), and `restore <id>` puts one back after saving the
current state first. `restore <id> --dry-run` shows exactly what it would
replace — and being read-only, it always works. The restore itself refuses to
run while Mod Organizer 2 or the game are still using the prefix (`--force`
overrides). The same buttons are in the GUI's Diagnostic view.

**Already have GAMMA on disk?** Don't download it twice. `stalker-gamma-linux
import /path/to/it` finds Anomaly and the Mod Organizer 2 instance by their
markers, adopts them where they are (symlinks if the layout differs — nothing is
copied or moved), and marks the downloads as done. `install` then only does what
is actually missing: ReShade removal, Proton prefix, MO2 configuration,
shortcut. Works for a manual install, a folder shared with a Windows dual-boot,
and for the [GOG one-click GAMMA that gets stuck in
Heroic](https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/issues/5063)
after downloading its 130 GB. Add `--dry-run` to see what it would adopt.

**Game crashing since yesterday, and nothing changed?** `stalker-gamma-linux
verify` hashes every file under `gamma/mods` and compares it to a reference
recorded on its first run (`gamma-md5.txt`, next to the install). It reports
what was modified, what disappeared and what you added, and attributes each
finding to the mod it belongs to. After the first run it only rereads the files
whose size or modification date moved, which takes a check that used to run for
minutes down to seconds — that catches everything written through the
filesystem (a truncated write, a file overwritten by another tool, an
interrupted extraction), and the report says how many files it took on trust.
Add `--full` to reread and rehash everything: that is the mode for content
altered *underneath* the filesystem, such as bit rot on a disk without
checksums, which leaves size and date untouched. `--repair` then removes just the damaged mods
that come from the modpack — folder plus cached archive — reruns the engine and
records a new reference. Only those mods are re-downloaded, but the engine
reinstalls the whole modpack over your mods folder, so other mods may be
updated in passing (measured on a real install: nothing removed, files you
added preserved). Files you added yourself are never deleted, and neither is a
mod folder that holds any of them: it is reported instead, for you to sort out
from Mod Organizer 2. The same two buttons are in the GUI's
Diagnostic view. Note this is a different check from `update`'s: that one
verifies the downloaded **archives**, this one the files actually on disk.

**Game crashed?** Close it, then run `stalker-gamma-linux postmortem` (or press
*Did the game crash?* in the GUI). It reads the engine's own log and tells you
how the session actually ended — and when the crash trace names a file, which
installed mods provide it. Those are **suspects**, not a verdict: the culprit can
be a mod that overrides one of them, and the wording says so. A session you
simply quit is reported as such, and a missing or truncated log gets a plain
"I cannot conclude" plus the path to look at, never a guess.

**Reporting a problem?** Run `stalker-gamma-linux doctor --report` (or click the
save icon in the GUI's Diagnostic view). It writes a single file with your
prerequisites, prefix state, installed Proton builds, that post-mortem verdict
with its trace excerpt, and the end of the log, with paths anonymized to `~` —
attach that to the issue and skip the back-and-forth. `stalker-gamma-linux --version` alone prints the version plus
the exact revision installed, which is what pins down *which* code you're on
between releases.

Every command has `--help`. `install` is resumable: interrupt it (Ctrl-C) and
rerun the same command — steps already completed (tracked in
`~/.config/stalker-gamma-linux/install-state.toml`) are skipped. Pass
`--verbose` (before the subcommand, e.g. `stalker-gamma-linux --verbose play`)
for debug output on the console; a full rotating log is always kept under
`~/.local/state/stalker-gamma-linux/`.

### GUI

The GUI (`stalker-gamma-linux-gui`) is a real **launcher**, not a generic
settings window: procedurally generated Zone artwork under a transparent
header, the GAMMA logo, a big PLAY/INSTALL button, and everything you need to
know at a glance — install target, and stat tiles for free disk space,
deployed mod count and launcher version. A live "system ready / N prerequisites
missing" pill sits in the title bar and opens the full Diagnostic view.

| | |
|---|---|
| ![Pré-installation](docs/screenshots/pre-installation.png) | ![Installation](docs/screenshots/installation.png) |

- **Guided install** — before anything is downloaded, a dialog shows the
  target directory, the free space on that volume with a colored verdict
  (enough / tight / insufficient — installation is blocked under 160 GiB,
  ~250 GiB recommended), and lets you pick another disk.
- **Real progress** — the install pipeline is rendered as a phase timeline
  (done / already done / running with live engine detail / pending), a real
  progress fraction (no fake pulsing bar), elapsed time, and an embedded
  console with the full engine log. Cancelling is clean and resuming skips
  validated steps.
- **Diagnostic** — same data as `doctor`, one glance verdict on top,
  copy-paste remediation commands per distro, and an **Installed mods** check
  that compares the mod files on disk to their reference fingerprint
  (*Check*), with a confirmed *Repair* for the damaged modpack mods.
- **Backups** — the same Diagnostic view lists every restore point (date,
  contents, size) with a *Restore* button each, and a *Back up now* that keeps
  your profiles, saved games and overwrite folder out of the rotation.
- **After a crash** — a *Did the game crash?* button appears on the main
  screen once you come back from a game, and tells you how the last session
  ended: a clean exit, a dead USVFS, or an engine crash — and in that case the
  mods that provide the files named in the trace, so you know which ones to
  disable first.

It needs GTK4 + libadwaita + PyGObject from your distribution (not
pip-installable — no manylinux wheel exists for PyGObject); running the
command without them prints the install command for your distro instead of
a raw traceback. It calls the exact same `orchestrator`/`mo2` code as the
CLI — no duplicated install logic — and never blocks the UI thread during a
download. The CLI remains fully independent and usable on its own.

The background artwork is generated deterministically by
`scripts/generate_background.py` (numpy + Pillow, fixed seed) — no external
asset, reproducible at any time. It draws the Zone at dusk (the Duga array, the
plant chimney, dead pylons, ground mist, an anomaly glow) in layers, then
grades the result; the same landscape is reused for the repository's social
card. The screenshots above are regenerated the same way, by
`scripts/capture_screenshots.py`: it builds every screen against a throwaway
demo install and renders it off-screen, so no personal path is ever published.

### Language

The CLI and GUI are in **English by default**, regardless of your system
locale. To switch language, set `LANGUAGE` explicitly, e.g.
`LANGUAGE=fr stalker-gamma-linux doctor`. French is fully translated today;
contributing another language is a normal gettext workflow, see
"Internationalisation" in `docs/ARCHITECTURE.md`.

## Legal

This repository contains **code and documentation only**. It never rehosts the
game, Anomaly, or any mod: everything is downloaded client-side from ModDB /
GitHub, exactly like the official GAMMA launcher does. All credit for GAMMA
goes to Grokitach and the modders listed at [stalker-gamma.com](https://stalker-gamma.com).

License: [GPL-3.0](LICENSE).
