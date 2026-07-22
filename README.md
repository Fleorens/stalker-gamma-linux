# stalker-gamma-linux

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
- GUI on top (GTK4/libadwaita), Flatpak/AppImage/AUR packaging

## How it works

We do **not** reimplement the modpack installation logic. The download/install
engine is [Mord3rca/gamma-launcher](https://github.com/Mord3rca/gamma-launcher)
(Python, GPL-3.0), which already handles ModDB mirror resolution, the GAMMA
modlist, extraction directives and MD5 verification. This project wraps it with
everything Linux-specific. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

🚧 Early stage — see [docs/ROADMAP.md](docs/ROADMAP.md) and [tasks/](tasks/) for
the work breakdown.

## Legal

This repository contains **code and documentation only**. It never rehosts the
game, Anomaly, or any mod: everything is downloaded client-side from ModDB /
GitHub, exactly like the official GAMMA launcher does. All credit for GAMMA
goes to Grokitach and the modders listed at [stalker-gamma.com](https://stalker-gamma.com).

License: [GPL-3.0](LICENSE).
