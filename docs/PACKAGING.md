# Packaging (T09)

Two distribution channels, each covering a different gap:

| Channel | Role | Ships | Build |
|---|---|---|---|
| **Flatpak** | Primary — full GUI + CLI, sandboxed, any distro incl. Steam Deck | GUI (`stalker-gamma-linux-gui`) + CLI (`stalker-gamma-linux`) | `make package-flatpak` |
| **AppImage** | Secondary — portable CLI for distros/setups where Flatpak isn't an option | CLI only, deliberately (see below) | `make package-appimage` |

AUR was in scope for T09 originally; dropped by explicit decision (2026-07-23,
Florian: "AUR je m'en tape") — Flatpak already covers Arch/Steam Deck users,
and `PKGBUILD` maintenance/testing needs an actual Arch machine this session
doesn't have. Not reflected anywhere else in the repo as a promised channel
(see the README/ROADMAP updates in this same commit).

Both channels build and run **locally, for real** (not just written and
hoped-for) as of this doc — see the two sections below for the exact commands
and what was actually verified on this machine.

## What's deliberately not bundled

- **libunrar** (RARLAB's proprietary RAR codec, used by `gamma-launcher`'s
  `unrar` Python dependency for `.rar` mod archives). Non-free license,
  incompatible with Flathub's bundling rules and with shipping it ourselves
  in the AppImage. This is *not a new gap*: it's the same one `doctor`
  already reports on native installs without RPM Fusion/AUR enabled
  (`environment/checks.py:check_libunrar`) — both packaged channels show the
  identical non-blocking warning. Florian's own real GAMMA install (779
  mods) completed without libunrar ever being present, which is the practical
  evidence that this is rarely if ever exercised by the actual modlist.
- **The game, Anomaly, or any mod.** Both channels were built and inspected
  for this: nothing under `packaging/` embeds anything beyond code, pinned
  upstream tool sources, and the project's own icon/desktop assets. Both
  `install`/`update` still do 100% of the actual downloading client-side, at
  first run, exactly like every other channel.

## Flatpak (`packaging/flatpak/`)

### Build & test

```sh
make package-flatpak
flatpak --user remote-add --if-not-exists --no-gpg-verify local-repo packaging/flatpak/.flatpak-repo
flatpak --user install --reinstall -y local-repo org.stalkergammalinux.Gui

flatpak run org.stalkergammalinux.Gui                                    # GUI
flatpak run --command=stalker-gamma-linux org.stalkergammalinux.Gui doctor # CLI
```

Both were run for real on this machine (GNOME 49 runtime): `doctor` prints
the full three-part report (environment/prefix/install state) and the GUI
renders its actual main window (screenshot taken and inspected during
development, not just "it didn't crash").

Requires `flatpak-builder` (`sudo dnf install flatpak-builder` or your
distro's equivalent) and the `org.gnome.Platform`/`org.gnome.Sdk` runtime,
version 49 — `flatpak install flathub org.gnome.Sdk//49` if not already
present. No other host prerequisite: every Python dependency is a pinned
wheel in `python3-requirements.json` (regenerated with
[`flatpak-pip-generator`](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip)
against `org.gnome.Sdk//49`, `--prefer-wheels` on the C-extension packages —
their sdists have broken standalone versioning outside a git checkout), so
the build never touches the network for Python packages, only for the two
git/archive module sources (gamma-launcher, p7zip, umu-launcher — all
pinned by tag/commit/sha256).

### Why GNOME runtime 49

Matches what's already installed on this machine and what Fedora ships
alongside GTK4 4.22 / libadwaita 1.9 (same versions T08 validated the GUI
against). The runtime already includes a working PyGObject with GTK4 +
libadwaita (`flatpak run --command=python3 org.gnome.Platform//49 -c "import
gi; ..."` succeeds) — no PyGObject module needed in the manifest.

### Modules and why each exists

- **`p7zip.yml`** — builds `7z`/`7za`/`7zr` from source
  (`p7zip-project/p7zip` v17.05, LGPL/public-domain). The sandbox can't see
  the host's `/usr/bin/7z`, so without this, `gamma-launcher`'s archive
  extraction would fail inside the Flatpak even on a system that has 7z
  installed natively.
- **`umu-launcher.yml`** — bundles the official self-contained "zipapp"
  release (single Python script, dependencies frozen inside). Same
  sandboxing reason as p7zip, plus a real host-side gap: umu-launcher has no
  PyPI package (`environment/commands.py`'s `pipx install umu-launcher` hint
  404s — confirmed while building this), so most hosts won't have `umu-run`
  on PATH either. This is exactly how Florian runs umu today on his own
  machine (manual zipapp install, see project history) — bundling it removes
  that manual step entirely for Flatpak users.
- **`python3-requirements.json`** — generated, not hand-written (see above).
  Covers `rich`, `tomli-w` (this project's own deps) and `gamma-launcher`'s
  declared dependencies (`beautifulsoup4`, `cloudscraper`, `GitPython`,
  `platformdirs`, `py7zr`, `requests`, `tenacity`, `tqdm`, `unrar` — the
  ctypes wrapper, not the codec; see "What's deliberately not bundled").
- **`gamma-launcher.yml`** — the engine itself, pinned to tag `v3.1` /
  commit `ade656e029a8547d8853ce1ba54f9b7f0acb9100` (same version pinned in
  `pyproject.toml`).
- **`stalker-gamma-linux.yml`** — this project, built from the local
  checkout (`type: dir`, `path: ../..`, with `.venv`/`.git`/caches excluded
  via `skip:`) — always packages what's actually on disk, which is what
  local iteration wants. **Not** what Flathub would accept for a real
  submission (see `flathub/README.md`).

### Permissions (`finish-args`) — one line each, no blanket grants

| Permission | Why |
|---|---|
| `--share=network` | Anomaly + GAMMA modpack + Proton-GE downloads (tens of GB, from ModDB/GitHub). |
| `--share=ipc` | Wine/X11 shared memory, needed by MO2 and the game regardless of windowing protocol. |
| `--socket=wayland` + `--socket=fallback-x11` | GTK4 UI natively on Wayland; MO2 and the game (Win32 GUI apps under Proton) still need real X11/Xwayland. |
| `--socket=pulseaudio` | Game audio (Wine → PulseAudio/PipeWire-pulse compat socket). |
| `--device=dri` | GPU acceleration: DXVK/VKD3D for the game, accelerated GTK4 rendering for the UI. |
| `--device=all` | Raw controller/gamepad input (Steam Deck built-ins, third-party pads) — no portal covers joysticks; same choice made by comparable Wine-launcher Flatpaks (Bottles, Lutris). |
| `--filesystem=host` | The install target is user-chosen and can be **any** mount (Florian's own real install lives on a second drive, not under any XDG location). Everything downstream — `gamma-launcher`, `umu-run`/Proton, `MO2.exe` under Wine — is a real subprocess chain needing genuine POSIX read/write, not a one-shot document-portal file descriptor. There is no narrower permission that covers "an arbitrary directory, read-write, for the whole session." |
| `--env=PYTHONPATH=...` | Not a sandbox permission — a Python-on-Flatpak fix. `sys.prefix` is `/usr` (that's where `/usr/bin/python3` lives), so `/app/lib/python3.13/site-packages` isn't on `sys.path` by default. Same fix Bottles uses for the same reason. |

### Known gaps, specific to the sandbox (not bugs)

Verified for real with `doctor` inside the installed Flatpak:

- **Steam / protontricks show MISSING even when installed on the host.**
  `--filesystem=host` grants *file* visibility, not PATH/exec access to host
  binaries — the sandbox always executes against its own `/app:/usr`. Since
  Steam integration is manual by design (T06) and protontricks is a
  documented fallback (umu is primary, T04), this doesn't block the golden
  path; `doctor` output makes the actual gap clear rather than silently
  failing later.
- **GPU Vulkan check (`vulkaninfo`) shows MISSING.** Diagnostic-only binary,
  not bundled (out of scope here); actual GPU access for gameplay/rendering
  goes through `--device=dri` + the runtime's GL extension, unaffected.
- **libunrar** — see "What's deliberately not bundled" above.

### SteamOS / Steam Deck scenario

The acceptance criterion is "runs on a SteamOS-like session, entirely in
user space, no `sudo`." Every command used above is `flatpak --user` /
`flatpak run` — nothing here ever touches a root-owned path, which is
exactly the constraint SteamOS's immutable root imposes on Desktop Mode
Flatpak apps. No actual Steam Deck was available to test on; the mechanism
is identical to what Valve ships Flatpak apps through, so this is confidence
by construction, not a live device test — worth being explicit about that
gap rather than overclaiming.

### Flathub submission — prepared, not sent

See `packaging/flatpak/flathub/README.md`. Staging script
(`flathub/collect.sh`) copies the current manifest set into the exact root
layout Flathub's own repo expects. Nothing has been pushed or opened as a
PR. The README also lists what would still need to change for a *real*
submission (pinned `stalker-gamma-linux` source instead of `type: dir`,
scalable icon, screenshots) — left undone here since none of it matters for
local packaging.

## AppImage (`packaging/appimage/`)

### Why the AppImage is CLI-only

The GUI needs GTK4 + libadwaita + PyGObject built against them. Bundling a
full GTK stack into an AppImage is its own specialized effort
(`linuxdeploy` + its GTK plugin, matching typelibs, icon themes,
gdk-pixbuf loaders...) — a different scope than "package a Python CLI",
and one the Flatpak channel already solves properly by relying on the
GNOME runtime instead of vendoring GTK by hand. So the two channels split
the work by what each is actually good at: Flatpak carries the GUI (sandboxed,
GTK provided by the runtime), the AppImage carries a portable CLI (no GTK
dependency at all) for hosts where Flatpak isn't installed or wanted. The
GUI stays reachable there too, just via `pip install .[gui]` +
`install.sh`, same as any native install.

### Build & test

```sh
make package-appimage
packaging/appimage/dist/stalker-gamma-linux-x86_64.AppImage doctor
```

Built and run for real on this machine; `doctor` produces the identical
three-part report as the native CLI (confirmed byte-for-byte comparable
output, host Steam/protontricks/Vulkan all correctly detected since the
AppImage — unlike the Flatpak — isn't sandboxed and inherits the normal
host `$PATH`).

`build.sh` is self-contained: it bootstraps its own tool venv
(`python-appimage`, in `.tool-venv/`, gitignored), builds p7zip from source
and downloads the umu-launcher zipapp (both cached under `.cache/`, reused
on subsequent builds), and produces
`dist/stalker-gamma-linux-x86_64.AppImage`. Nothing needs to pre-exist
beyond Python 3, a C++ toolchain, and network access — CI-able as-is.

### Base image and portability

`python-appimage`'s prebuilt Python 3.11 base image, `manylinux2014`
variant (the older/broader glibc baseline available for 3.11, picked
automatically — broader compatibility across older host distros than
`manylinux_2_28`).

### What's bundled and why (same reasoning as Flatpak, different mechanism)

AppImages aren't sandboxed — they inherit the host's `$PATH` — so in
principle host-installed `umu-run`/`7z` would already work. They're bundled
anyway (under `$APPDIR/usr/bin`, prepended to `PATH` by `entrypoint.sh`) for
the same practical reason as the Flatpak: umu-launcher has no PyPI package
and inconsistent distro packaging, so "self-contained" should actually mean
self-contained rather than "works if you already happened to install umu
some other way." `gamma-launcher` and this project's own dependencies come
from `requirements.txt.in` (templated into `requirements.txt` per build,
gitignored — the last line is the absolute path to the checkout, which is
machine-specific).

### Two upstream quirks hit and worked around (documented in-line where they bite)

- `python-appimage`'s dependency-install step shells out **unquoted**
  (`utils/system.py`: `' '.join(args)` through `subprocess.Popen(...,
  shell=True)`). A PEP 508 `name @ url` requirement (spaces around `@`)
  gets word-split and breaks pip — fixed by using the bare `git+` URL form
  instead (see the comment in `requirements.txt.in`).
- The final packaging step has the same unquoted-shell issue with the
  `.desktop` file's `Name=`, which becomes the output filename — a
  display-style name with spaces/parens ("S.T.A.L.K.E.R. G.A.M.M.A.
  (CLI)") breaks `appimagetool`'s invocation. Fixed by keeping `Name=` a
  plain identifier (`stalker-gamma-linux`); see the comment in
  `stalker-gamma-linux.desktop`.
- `stalker_gamma_linux.cli` has no `if __name__ == "__main__"` guard (by
  design: it's meant to be reached through the pip-generated console-script
  entry point, not run as `-m stalker_gamma_linux.cli`). `entrypoint.sh`
  calls `$APPDIR/usr/bin/stalker-gamma-linux` (the real entry point) rather
  than `-m`, which would otherwise import the module, do nothing, and exit
  0 silently — worth knowing if this entrypoint is ever "simplified" back
  to a `-m` call.

## Local build cache layout (gitignored, not cleaned by `make clean-packaging`)

`packaging/appimage/.cache/` holds the built p7zip tree and the downloaded
umu-run zipapp across builds — deliberately not wiped by `clean-packaging`
(that target only clears build *outputs*, not this reusable cache) since
rebuilding p7zip from source takes real time. Delete it by hand if you need
a fully from-scratch build.
