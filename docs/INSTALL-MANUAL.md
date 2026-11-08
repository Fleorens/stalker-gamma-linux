# Manual installation of S.T.A.L.K.E.R. G.A.M.M.A. on Linux — reference specification

> **Role of this document**: it is the complete manual procedure that
> `stalker-gamma-linux` must automate (main mode: **MO2 under
> Proton**). Each step gives the exact commands and a verification
> criterion. Uncertain points are marked `⚠ TO CONFIRM` — to
> confirm on a real machine before automating.
>
> Written on 2026-07-19 from the cross-referenced sources listed at the end
> of the document. Main reference guide: v1ld's gist (updated Sept.
> 2025, protontricks + Steam method).

## 0. Overview

```
gamma-launcher (Python) ──► downloads Anomaly + the ~400 mods (ModDB/GitHub)
                            and builds the MO2 instance in gamma/
Steam + Proton          ──► runs ModOrganizer.exe (non-Steam game)
protontricks            ──► injects the required Windows DLLs into the prefix
MO2 (under Proton)      ──► launches Anomaly with the mods mounted via USVFS
```

Key points validated by the sources:
- MO2 + USVFS **work** under Proton (with a known CPU overhead);
  it is the method recommended by all recent guides.
- The prefix used is the one created by Steam for the non-Steam game
  `ModOrganizer.exe` → MO2 and the game naturally share the same prefix.
- ReShade must be removed (incompatible with DXVK) — required step.

### Notable divergences between the sources

| Topic | v1ld (2025, ref.) | FaithBeam wiki | maxastyler (Deck, old) |
|---|---|---|---|
| winetricks verbs | `d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 dx8vb quartz vcrun2022` (+`cmd` optional) | `d3dcompiler_43 d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 vcrun2022` | `d3dcompiler_43 d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 d3dx9_43` |
| Proton | Proton **9/10 vanilla** via Steam | proton-ge-9-20 | not specified |
| Prefix tool | protontricks (Steam prefix) | winetricks/protontricks | protontricks (Discover) |
| Disk space | 17 + 83 + 46 GB ≈ **146 GB** | n/a | n/a |

Decisions for automation: start from the **union of the verbs** then
prune by tests. **Pruning done (2026-08-15)** — the retained list is
`vcrun2022 d3dcompiler_43 d3dcompiler_47 d3dx9 d3dx10 d3dx11_43`, without
`dx8vb` nor `quartz` : the first is the DirectX 8 typelib for *Visual
Basic* (X-Ray is in C++ and ships its own DX8/9/10/11 renders), the
second is the DirectShow runtime, while Anomaly ships no file
video nor codec. The maintainer's real prefix: these 6 verbs, nothing else, game
working. Proton: user decision (2026-07-19) —
**latest GE-Proton release by default** (or Proton Experimental from Steam
if it is present and no GE is); reports flagging
MO2 issues with certain GE versions will be arbitrated by the T05 matrix.

---

## 1. System requirements

### Disk space

| Folder | Size (Sept. 2025) |
|---|---|
| `anomaly/` (base game) | ~17 GB |
| `gamma/` (MO2 + mods) | ~83 GB |
| `cache/` (downloaded archives) | ~46 GB |
| **Total during installation** | **~146 GB** |

The official figure "27 GB downloaded / 76 GB installed" (Grokitach wiki)
is underestimated for our pipeline because the cache is kept for the
updates. The cache can be purged after install if space is short
(but any update will re-download).

### Required packages

Fedora:
```bash
sudo dnf install python3 python3-virtualenv p7zip p7zip-plugins unrar protontricks
# unrar is in RPM Fusion ; otherwise libunrar via https://www.rarlab.com
```

Arch:
```bash
sudo pacman -S python python-virtualenv p7zip protontricks
yay -S libunrar        # AUR
```

Debian/Ubuntu:
```bash
sudo apt install python3 python3-venv p7zip-full libunrar5 protontricks
# ⚠ TO CONFIRM: exact name of the libunrar package according to the Debian/Ubuntu version
```

Plus: **Steam** (native if possible; Flatpak works but protontricks
must then be the Flatpak `com.github.Matoking.protontricks` and the
disk extended with Flatseal — `⚠ TO CONFIRM`).

**Verification**: `protontricks --version`, `7z`, `python3 --version`
(≥ 3.10) respond; `df -h` shows ≥ 150 GB free on the target.

### Hardware
- Working Vulkan GPU (`vulkaninfo --summary` lists a device).
- 16 GB of RAM recommended (8 GB = swap advised during install).

---

## 2. Installing gamma-launcher

Three methods (in order of preference for automation):

**a) venv + pip (recommended, reproducible)**:
```bash
git clone https://github.com/Mord3rca/gamma-launcher
cd gamma-launcher
git checkout <latest release tag>          # e.g. v3.1 — pin it, not master
python3 -m venv .venv && source .venv/bin/activate
pip install setuptools                     # required Python ≥ 3.12
pip install .
```

**b) Release binary** (self-contained, built on Ubuntu): download from
https://github.com/Mord3rca/gamma-launcher/releases, `chmod +x`.
Known pitfall: `symbol lookup` error on certain distros → run with
`LD_PRELOAD=/usr/lib/libreadline.so ./gamma-launcher`.

**c) AUR** (Arch): `yay -S gamma-launcher`.

**Verification**: `gamma-launcher --help` lists the subcommands
(`anomaly-install`, `full-install`, `check-md5`, …).

---

## 3. Structure and installation of Anomaly

```bash
mkdir -p ~/Games/stalker-gamma/{anomaly,gamma,cache}
gamma-launcher anomaly-install --anomaly ~/Games/stalker-gamma/anomaly
```

The launcher downloads Anomaly 1.5.1 + patch 1.5.2 from ModDB (large
download, resumable by re-running).

⚠ Absolute rule: **paths without spaces or special characters** (the
paths cross the Linux→Windows boundary via Wine; spaces are
a classic source of crashes).

**Verification**:
```bash
gamma-launcher check-anomaly --anomaly ~/Games/stalker-gamma/anomaly
ls ~/Games/stalker-gamma/anomaly/AnomalyLauncher.exe   # must exist
```

---

## 4. Installing the G.A.M.M.A. modpack

```bash
gamma-launcher full-install \
  --anomaly ~/Games/stalker-gamma/anomaly \
  --gamma   ~/Games/stalker-gamma/gamma \
  --cache-directory ~/Games/stalker-gamma/cache
```

What this command does: fetch the modpack definition
(Grokitach/Stalker_GAMMA + api stalker-gamma.com), resolve the ModDB links,
download ~400 archives into the cache, extract them according to the directives
of installation, and build the MO2 instance in `gamma/` (mods, profiles,
`ModOrganizer.exe`).

This is long (depends on the bandwidth; ModDB rate-limits). **Interruption = no
problem**: re-running the same command resumes from the cache.

Known pitfalls:
- `ModDB download link not found` (upstream issue #167): dead mirror on the
  ModDB side, usually fixed upstream — update gamma-launcher and
  re-run.
- Python 3.14: py7zr extraction bug on large archives
  (workaround documented in the comments of the v1ld gist).

**Verification**:
```bash
gamma-launcher check-md5 --gamma ~/Games/stalker-gamma/gamma   # 0 errors
ls ~/Games/stalker-gamma/gamma/ModOrganizer.exe
ls ~/Games/stalker-gamma/gamma/profiles/                        # G.A.M.M.A profile present
```

---

## 5. Removing ReShade (required)

ReShade (injected by the modpack for Windows) does not work under
DXVK/Proton and breaks the rendering or the launch:

```bash
gamma-launcher remove-reshade --anomaly ~/Games/stalker-gamma/anomaly
gamma-launcher purge-shader-cache --anomaly ~/Games/stalker-gamma/anomaly
```

Cosmetic equivalent on Linux: **vkBasalt**, now provided by the tool
with its "ReShade-like" preset (`play --vkbasalt`, or the switch of
Preferences) — see docs/ARCHITECTURE.md "Performance layers". In
manual installation: `ENABLE_VKBASALT=1` in front of the launch command, the
layer then reads your own `~/.config/vkBasalt/vkBasalt.conf`.

**Verification**: no more `ReShade*.dll` / `reshade-shaders/` in
`anomaly/bin/` ; `anomaly/appdata/shaders_cache/` empty or missing.

---

## 6. Non-Steam game + Proton prefix

### 6.1 Adding to Steam
1. Steam → *Add a game* → *Add a non-Steam game* → browse to
    ~/Games/stalker-gamma/gamma/ModOrganizer.exe.
2. Entry properties → *Compatibility* → check *Force the use of
    a compatibility tool* → **Proton 9 or 10 (vanilla)**.
3. Run the entry once from Steam (MO2 may or may not display),
    then quit: this first launch **creates the prefix**.

**Verification**: a new folder
~/.steam/steam/steamapps/compatdata/<APPID>/pfx/ has appeared (APPID
negative/large number = non-Steam game; `protontricks -l` shows it).

### 6.2 Injecting the Windows DLLs

```bash
protontricks -l          # locate the APPID of "ModOrganizer.exe" / the shortcut
protontricks <APPID> d3dcompiler_43 d3dcompiler_47 d3dx9 d3dx10 d3dx11_43 \
                     dx8vb quartz vcrun2022
```

Notes:
- Do **not** install `dxvk` via winetricks (Proton already ships it).
- SHA hash warnings on `vcrun2022` : ignorable (upstream source).
- `cmd` is listed by v1ld but sometimes fails → optional, skip on error.
- `dx8vb`/`quartz` (only in v1ld): **excluded**, see the table of
   divergences above. `quartz` remains the first remedy to try if a
   video refuses to play — troubleshooting, not a requirement.
- `d3dcompiler_43` (absent in v1ld): **kept**, it is present in the
   other two sources and costs nothing.

**Verification**:
```bash
ls ~/.steam/steam/steamapps/compatdata/<APPID>/pfx/drive_c/windows/system32/d3dcompiler_47.dll
```

### 6.3 Steamless variant (umu-launcher) — target path for automation

**Verified in reality on 2026-07-19** (umu 1.4.1, GE-Proton11-1, Fedora 44) for
prefix creation and verb injection — it is the main path
of `stalker-gamma-linux` (T04, `prefix-doctor --repair`). The launch of MO2
of the game via umu is **implemented and verified in T05** (`mo2/launch.py`,
commands `mo2` and `play`). **Verified in reality on 2026-07-22** (umu 1.4.1,
GE-Proton11-1, 93 GB GAMMA install): MO2 opens, `play` launches Anomaly DX11
via `moshortcut://:Anomaly (DX11)`, USVFS is mounted (577 mods served) and part runs.

```bash
# prefix-only creation (official umu sentinel, launching nothing) :
WINEPREFIX=~/Games/stalker-gamma/prefix GAMEID=umu-stalkergamma \
  PROTONPATH=<compatibilitytools.d>/GE-ProtonX-Y umu-run createprefix
# verbs (one at a time; protonfixes ships winetricks) :
WINEPREFIX=... GAMEID=... PROTONPATH=... umu-run winetricks -q vcrun2022
# MO2 (interface) — equivalent of `stalker-gamma-linux mo2` :
WINEPREFIX=... GAMEID=... PROTONPATH=... umu-run \
  ~/Games/stalker-gamma/gamma/ModOrganizer.exe
# game via MO2 (USVFS) — equivalent of `stalker-gamma-linux play` :
WINEPREFIX=... GAMEID=... PROTONPATH=... umu-run \
  ~/Games/stalker-gamma/gamma/ModOrganizer.exe "moshortcut://:Anomaly (DX11)"
```

T05 finding (umu 1.4.1 + GE-Proton11-1, **new** prefix on another disk):
umu-run createprefix **does create** the prefix ("Upgrading prefix from None…")
but umu then tries to *launch* the sentinel as an executable and exits with
**a non-zero code** (`ShellExecuteEx: Fichier introuvable`). `create_prefix` treats
therefore the prefix initialization (`system.reg`), and not the return code, as
truth: command failure + initialized prefix = success.

Findings of the real test: umu creates the prefix *flat* in `WINEPREFIX` with
a symlink `pfx -> .` ; the Wine output contains non-UTF-8 bytes (read
with a tolerant decoding); the first run downloads the Steam runtime
(`steamrt4`, ~500 MB) in `~/.local/share/umu/`. A desktop shortcut
`.desktop` is then installed (T06); adding to Steam as a non-Steam game
(for Steam Input / Gaming mode) remains, for its part, manual via the native button of
Steam — cf. §6.1.

---

## 7. Configuring Mod Organizer 2

Re-run the Steam entry (MO2 opens in the equipped prefix):

1. If MO2 asks for the instance type: **portable instance** (the instance
   delivered by GAMMA in `gamma/` is portable).
2. MO2 reports that the Anomaly path is invalid (expected: the instance was
   built outside Wine) → point to the game folder:
   `Z:\home\<user>\Games\stalker-gamma\anomaly` (Linux paths are seen
   via the `Z:` drive in the prefix).
   Known behavior: MO2 goes from game folder → instance folder
   without explicit confirmation — that's expected, instance = `gamma/`.
3. Check in the top right that the active profile is **G.A.M.M.A** and that
   the selected executable is **Anomaly (DX11)** (or
   `AnomalyLauncher.exe` in the right panel depending on the version of
   the instance).

Automation **implemented (T05)**: `mo2/instance.py` writes these values
directly into `ModOrganizer.ini` by surgical editing, removing any
interaction. Confirmed on a real GAMMA instance: `gameName=STALKER Anomaly`,
`selected_profile=@ByteArray(G.A.M.M.A)`, `gamePath` in `@ByteArray(Z:\...)`
(backslashes doubled). The executables ("Anomaly (DX11)"…) are
`[customExecutables]` with **baked-in absolute paths** to the old folder
Anomaly (`binary`/`workingDirectory` with forward slashes, `arguments` with
doubled backslashes): `configure_instance` **rebases** them to the real folder
so that `moshortcut://` targets the right binary. The command
stalker-gamma-linux mo2 configures then opens MO2. `mo2/session.resolve_anomaly`
tolerates both layouts: `<install>/anomaly` (project) and `<gamma>/anomaly`
(GAMMA, Anomaly nested in the instance).

**Verification**: the left column of MO2 lists the ~400 GAMMA mods,
checked, without a blocking warning triangle.

---

## 8. First launch of the game

1. In MO2: executable **Anomaly (DX11)** → *Run*.
2. First launch is long (DXVK shader compilation) — do not kill the
   process for several minutes.
3. In the main menu: check for the presence of the GAMMA menu/HUD (proof
   that USVFS mounts the mods correctly — a vanilla Anomaly at launch =
   USVFS dead, see §9).

Recommended settings for first run: DX11 renderer, windowed fullscreen
first (alt-tab safer under Wine), then fullscreen.

**Final verification**: a new game loads in the starting zone;
the screen shows no major artifacts (otherwise → §5 ReShade/shaders).

---

## 9. Known pitfalls and remedies

| Symptom | Likely cause | Remediation |
|---|---|---|
| The game launches **vanilla** (no GAMMA content) | USVFS does not mount (incompatible Proton version) | Detected by `play` (USVFS diagnostics); matrix `docs/MO2-PROTON-COMPAT.md` : Proton 9/10 vanilla → GE-Proton9-20; last resort: `play --flat` (Annex A) |
| Crash/black screen at launch | ReShade still present | §5 (`remove-reshade` + `purge-shader-cache`) |
| Visual artifacts, broken shaders | Outdated shader cache after update | `purge-shader-cache` + delete `anomaly/appdata/shaders_cache` |
| Poor perf on large shader mods (especially Deck) | Screen Space Shaders / Shaders Cumulative Pack too heavy | Disable these mods in MO2 (source: maxastyler guide) |
| `ModDB download link not found` during full-install | Dead ModDB mirror | Update gamma-launcher, re-run (cache kept) |
| MO2 does not start at all | Missing verbs in the prefix | Re-run §6.2; check vcrun2022 |
| `symbol lookup` error with the release binary | Bundled libreadline | `LD_PRELOAD=/usr/lib/libreadline.so` |
| Random extraction crash (Python 3.14) | py7zr bug on large archives | venv on Python 3.11–3.13, or system 7z patch (gist v1ld) |
| Paths with spaces | Wine translation of paths | Reinstall in a path without spaces |

USVFS performance: the Windows→Wine hooking adds a CPU overhead
(context-switching). An optimization lead identified: **RadTux** (native VFS
Linux replacing MO2's USVFS hooks) — experimental, tested on
Fallout 4/MO2 2.5.2, `⚠ TO CONFIRM` for GAMMA → to be evaluated in T05.

---

## Annex A — Flat mode (fallback without MO2)

Only if MO2 refuses to work on the config:

```bash
gamma-launcher usvfs-workaround \
  --anomaly ~/Games/stalker-gamma/anomaly \
  --gamma   ~/Games/stalker-gamma/gamma \
  --final   ~/Games/stalker-gamma/flat
```

Produces a playable merged installation without MO2 (run
`AnomalyLauncher.exe` from the `flat/` folder under Proton). **Loss of the
mods flexibility** (no more enable/disable) — it's a fallback,
not the nominal mode of this project.

## Annex B — Steam Deck notes

- The §1-8 procedure applies (SteamOS has protontricks via Discover;
  gamma-launcher as a release binary or via distrobox — `⚠ TO CONFIRM` :
  does the Ubuntu binary run as-is on SteamOS ?).
- Install on microSD: possible but paths
  `/run/media/mmcblk0p1/...` — watch out for ext4/btrfs formatting (no
  FAT: symlinks / name case break the install).
- Reported perf: ~60 FPS overall, ~40 FPS base Clear Sky; disable
  the heavy shader mods (§9) improves it considerably.
- Gaming mode: the non-Steam entry appears normally; provide a
  community controller layout (SteamInputDB offers some for GAMMA).

## Annex C — Context: GOG distribution

End of 2025, GOG added G.A.M.M.A. as "one-click mod". The first version
of this annex concluded "Galaxy is Windows-only, so no direct impact
for Linux": it is **false**, and verified as such on 2026-08-15. The
Linux players go through **Heroic**, and the install blocks there after the
download — 130 GiB on disk, blocked at 100% on "Processing
files", workaround by cancelling then importing the files, after which
the game does not start correctly (Heroic#5063).

Consequence for this project: there is an audience that already has the files
and no usable install. It is exactly what the command
`import` adopts (see `adopt.py`) — detection by markers, symlinks
if the layout differs, no byte re-downloaded.

The remaining lead, unexplored: GOG hosts the pack, which could offer in
time a download source alternative to ModDB (and thus to the wall
Cloudflare).

---

## Sources

- v1ld gist (reference guide, Sept. 2025):
  https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
- Mord3rca/gamma-launcher (engine, commands):
  https://github.com/Mord3rca/gamma-launcher
- FaithBeam/stalker-gamma-cli Linux wiki:
  https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Official GAMMA wiki (Windows target behavior):
  https://github.com/Grokitach/Stalker_GAMMA/wiki/Installing-GAMMA
- Steam Deck guide (maxastyler):
  https://github.com/maxastyler/S.T.A.L.K.E.R.-Gamma-Steam-Deck-Install-Guide/
- USVFS under Wine (MO2 compat thread):
  https://github.com/ModOrganizer2/modorganizer/issues/372
- RadTux (experimental native VFS for MO2):
  https://www.nexusmods.com/fallout4/mods/105285
- GOG one-click GAMMA (GamingOnLinux, Dec. 2025):
  https://www.gamingonlinux.com/2025/12/gog-add-stalker-gamma-as-a-one-click-mod-install/
