# Architecture

## Principle

Three layers. We only rewrite what is specific to Linux.

```
┌─────────────────────────────────────────────┐
│  GUI (GTK4/libadwaita) — phase 3            │
├─────────────────────────────────────────────┤
│  stalker-gamma-linux (ce repo)              │
│  - CLI orchestrateur (install/update/play)  │
│  - Détection environnement & prérequis      │
│  - Gestion préfixe Proton (umu, Proton-GE,  │
│    verbs winetricks)                        │
│  - MO2 sous Proton (mode principal)         │
│  - Raccourci bureau (.desktop + icône)      │
│  - Install natif (install.sh, pas de sandbox)│
├─────────────────────────────────────────────┤
│  Moteur : Mord3rca/gamma-launcher (GPL-3.0) │
│  - Résolution miroirs ModDB, téléchargement │
│  - Parsing modlist GAMMA, directives        │
│  - anomaly-install, full-install, update,   │
│    check-md5                                │
└─────────────────────────────────────────────┘
```

## Decisions made

1. **Option B**: wrapper above `gamma-launcher`, no rewrite of the engine. We
   benefit from upstream maintenance when the modpack changes.
2. **MO2 under Proton is the main mode** (user decision): this is what works
   today and what preserves mod flexibility (enable/disable/add). The « flat »
   mode (`usvfs-workaround`) is only a documented fallback for configs where MO2
   does not run.
3. **Single prefix**: MO2 and the game live in the *same* Proton prefix. MO2
   launches `AnomalyLauncher.exe`/the game through its USVFS, so both must share
   the prefix. Required verbs: `vcrun2022`, `d3dcompiler_43`, `d3dcompiler_47`,
   `d3dx9`, `d3dx10`, `d3dx11_43`.
4. **Proton-GE via umu-launcher** preferred over protontricks when possible:
   works outside Steam, scriptable, reproducible.
5. **ReShade is removed** (incompatible with DXVK); vkBasalt proposed as an
   equivalent.
6. **Python** everywhere (consistency with the engine), packaging
   via `pyproject.toml`.
7. **No rehosting ever**: the repo contains only code. All downloads (Anomaly,
   mods) happen client-side from ModDB/GitHub.

## Target layout of an installation

```
~/Games/stalker-gamma/            # configurable
├── prefix/                       # préfixe Proton partagé (MO2 + jeu)
├── anomaly/                      # jeu de base (archives ModDB)
├── gamma/                        # MO2 + mods + profils GAMMA
│   ├── ModOrganizer.exe
│   ├── mods/
│   └── profiles/G.A.M.M.A/
└── cache/                        # archives téléchargées (reprise/update)
```

## gamma-launcher engine integration (T03)

### Decision: subprocess, not direct import

The `engine/` module drives `gamma-launcher` (tag `v3.1` studied) by launching
the installed binary (`gamma-launcher <sous-commande> ...`) via `subprocess`,
and not by importing `launcher` as a Python library. Reasons, observed by
reading the v3.1 source code:

1. **`CheckMD5.run()` calls `sys.exit()` directly**
   (`launcher/commands/check.py`). Importing and calling this method in-process
   would kill the calling process. `CheckAnomaly.run()`, on the contrary,
   raises a `RuntimeError` on failure, and other commands settle for a silent
   return. The failure semantics are inconsistent from one command to the next
   on the Python side; on the process side they are instead **uniform**: return
   code 0 = success, non-zero = failure, whatever the internal mechanism. The
   subprocess normalizes this for us for free.
2. **No progress API**: the commands do `print()` (steps,
   stdout) and use `tqdm` (byte-by-byte download progress, stderr by default).
   No callback/hook is exposed. Whether we import it or launch it as a
   subprocess, we have to *parse a text output* to extract progress from it — so
   the subprocess costs nothing more here, and also isolates our calling process
   from an upstream crash or a `sys.exit`.
3. **Undocumented and unstable internal classes**: `AnomalyInstall`,
   `FullInstall`, etc. expect an `argparse.Namespace` with precise attributes
   (`anomaly_verify`, `cache_path`, `mo_version`, `custom_def`, …) that are
   neither a public contract nor stable — `git diff v2.6 v3.1` shows changes in
   `commands/install.py` and `commands/check.py` between these two releases. The
   real stable contract, documented in the upstream README and used by all guides
   (T01), is the **CLI** (`gamma-launcher
   <sous-commande> --anomaly ... --gamma ...`), not the Python classes.
4. **Heavy dependencies avoided**: importing `launcher` would pull
   `cloudscraper`, `py7zr`, `GitPython`, `unrar`, `tenacity`, `tqdm`,
   `beautifulsoup4` into the same environment/process as
   `stalker-gamma-linux`. As a subprocess, `gamma-launcher` can even run in a
   different interpreter/venv — useful for the documented workaround of the
   `py7zr` extraction bug on Python 3.14 (see
   `docs/INSTALL-MANUAL.md` §4, pitfalls table).
5. **Hidden state to neutralize**: `launcher.cli.main()` remembers
   `--anomaly`/`--gamma`/`--cache-directory` in a persistent `config.ini`
   (`platformdirs`) and re-injects them automatically on subsequent calls via
   `argv.insert(2, '@config.ini')`. We disable this mechanism by passing
   `GAMMA_LAUNCHER_NO_CONFIG=1` in the subprocess environment, so
   our explicit paths are always the only source of truth.

In short: the subprocess is the *robust* choice here, not a stopgap — the
internal Python API of gamma-launcher is precisely not designed to be called as
a library (it calls `sys.exit`, it prints instead of raising events, it is not
versioned as such).

### Subcommand ↔ `engine/` function mapping

| `engine/` function | gamma-launcher subcommand(s) | Notes |
|---|---|---|
| `install_anomaly(paths)` | `anomaly-install --anomaly --cache-directory` | |
| `install_gamma(paths)` | `full-install --anomaly --gamma --cache-directory` | Idempotent upstream: reinstalls what is missing, updates otherwise. |
| `update_gamma(paths)` | *identical to `install_gamma`* | **gamma-launcher v3.1 has no separate `update` subcommand** (unlike what the T03 prompt assumed) — `full-install` already checks `revision.txt` and re-downloads/re-applies only what changed. `update_gamma` is a documented alias of `install_gamma`. |
| `verify(paths)` | `check-anomaly --anomaly` then `check-md5 --gamma` | The two cover different files (game binaries vs mod archives); we chain them for a single `verify()` call. |

### Shared cache and resume

`--cache-directory` is used by gamma-launcher only during the **first**
`gamma-setup` (invoked by `full-install` if `gamma/mods/` does not yet exist):
at that point, `gamma/downloads` is replaced by a **symlink**
to our `cache/` (see `launcher/commands/install.py:GammaSetup.run`,
`downloads_dir.symlink_to(cache_dir)`). That is why `check-md5` (which
hard-reads `gamma/downloads`, without a `--cache-directory` option) sees our
cached files. As long as we always re-point `--cache-directory`
to `cache/` and never delete it between two calls, re-running
`install_gamma`/`update_gamma` after an interruption resumes on the
archives already present and verified (`use_cached=True` upstream) — no
resume logic to reimplement on the `stalker-gamma-linux` side.

## Proton prefix management (T04)

The `prefix/` module creates and maintains the **unique and shared** prefix
(decision 3) in `<install>/prefix/`, via **umu-launcher** (decision 4).

### Implementation choice

1. **umu = main route, protontricks = documented fallback.** umu is
   scriptable outside Steam and lets you choose the prefix location. The
   protontricks fallback (docs/INSTALL-MANUAL.md §6.1-6.2) requires an existing
   Steam entry — so an APPID, which the user creates themselves via
   *Ajouter un jeu non-Steam* (T06 does not automate it) — and clicks in Steam:
   it stays manual, it is not automated here. `UmuNotFoundError`
   points to this fallback.
2. **Prefix layout**: we pass `WINEPREFIX=<install>/prefix` to umu.
   Verified for real (umu 1.4.1, 2026-07-19): umu creates the prefix **flat**
   in this directory and adds a compatibility symlink `pfx -> .`
   (Proton compatdata layout). `PrefixPaths.wine_root` absorbs both
   layouts. `GAMEID=umu-stalkergamma` fixes the protonfixes key.
3. **Creation**: the `createprefix` sentinel of umu-run (initializes the
   prefix without launching anything). Verified for real: official umu 1.4.1
   sentinel (empty string or `createprefix` in `umu_run.py`); prefix creation
   observed (« Upgrading prefix from None to GE-Proton11-1 »). After
   creation we check `system.reg`.
4. **Verb idempotence**: the source of truth is the `winetricks.log`
   that winetricks keeps itself at the root of the prefix (including one placed
   by protontricks, which delegates to winetricks). We apply only the missing
   verbs, **one at a time**: attributable failure, and each successful verb is
   recorded — a re-run plays only the rest.
5. **Proton version** (user decision, 2026-07-19): the **latest
   GE-Proton release** by default. Preference order: the most recent GE already
   installed (detection in known `compatibilitytools.d` — native Steam,
   `~/.steam`, Flatpak; umu also installs its own there) → **Proton
   Experimental** of Steam (`steamapps/common/Proton - Experimental`) →
   any other present build → download of the latest published GE release
   (resolved via the GitHub API, pinned fallback `GE-Proton11-1` if the API is
   rate-limited) with SHA-512 verification against the published `.sha512sum`,
   extraction to a temporary directory then rename — no residue on failure. The
   recommendation « Proton 9/10 vanilla » of the guides is
   replaced by this decision; if the MO2/GE matrix (T05) reveals an
   issue, it will arbitrate it.
6. **Any external command** goes through `run_in_prefix()`: output captured
   in `<install>/logs/*.log`, non-zero code ⇒ `PrefixCommandError` with the
   log path and last lines. Decoding with
   `errors="replace"`: Wine emits non-UTF-8 bytes (crash observed for real with
   strict decoding). The structural variables
   (`WINEPREFIX`, `GAMEID`, `PROTONPATH`) are imposed last:
   the caller (T05/T06/T07) cannot break the shared-prefix invariant.
7. **`prefix-doctor`** checks umu, Proton, initialization, verbs and DXVK
   (marker `DXVK` in the system32 `d3d11.dll`/`dxgi.dll` — Wine's builtins do
   not have it); `--repair` re-runs the idempotent provisioning.

## MO2 under Proton — main mode (T05)

The `mo2/` module runs Mod Organizer 2 in the shared prefix with
**USVFS active**: this is the game-side reason for the project (mod
flexibility). Breakdown:

1. **Instance configuration (`instance.py`)** — the step gamma-launcher
   does not do. The MO2 instance livrée by GAMMA is built outside Wine, so its
   `gamePath` is invalid. We edit it **surgically** in
   `ModOrganizer.ini`: `gamePath` → the Anomaly folder in **Windows path**
   form (`Z:\...`, translated by `winepath.py`), `selected_profile` → `G.A.M.M.A`.
   We never rewrite the whole file (`ini.py` replaces line by line): MO2
   serializes Qt blobs there (`@ByteArray(...)`, `[customExecutables]`) that a
   `configparser` would corrupt. `.bak` backup of the original file, idempotent.
2. **Launch (`launch.py`)** — we never launch the game exe directly
   (USVFS is local to the MO2 process). `launch_mo2()` opens the interface;
   `launch_game()` passes to `ModOrganizer.exe` the URI `moshortcut://:Anomaly (DX11)`
   (portable instance = empty instance part), which mounts USVFS and launches the
   game through it. Everything goes through `run_in_prefix` (T04).
3. **Diagnostics (`diagnostics.py`)** — symptom #1: game launched « vanilla »
   (dead USVFS). After a launch, we read the last `logs/usvfs-*.log` of
   the instance: marker `proxy run successful` ⇒ VFS mounted; absent ⇒ USVFS
   probably dead. We also check that the profile has active mods (`modlist.txt`).
   The remedies point to `docs/MO2-PROTON-COMPAT.md`.
4. **Proton version**: arbitrated by `docs/MO2-PROTON-COMPAT.md`. Default =
   latest GE (decision T04); documented fallback to Proton 9/10 *vanilla* if the
   diagnostics detect a dead USVFS.
5. **Flat fallback (`flat.py` + `merge.py`)** — accessible only via flag
   explicit (`play --flat`). Fuses Anomaly + the mods **by hard links**,
   then launches `AnomalyLauncher.exe` from the fused folder. **Loss of the
   mod flexibility** — hence the flag and the warning
   (docs/INSTALL-MANUAL.md annex A).

    *The only assumed divergence from the upstream engine*, and it is
    measured: `gamma-launcher usvfs-workaround` does `copytree` (verified in its
    v3.1 code, `commands/usvfs.py`), so the fallback cost a second complete
    installation — ~100 GiB. A hard link gives the same tree for a few inodes. We
    only reimplement the fusion: ModDB resolution, directive parsing and MD5
    verification stay with gamma-launcher. The fix is meant to go upstream
    (option `--link`).

    Two rules that `merge.py` applies and which are not obvious:
    the application order follows `modlist.txt` **from bottom to top** (increasing
    priority towards the top in MO2, so the highest-priority mod overwrites last),
    and everything that lives under `appdata/` is **copied, never linked** —
    the game rewrites its settings and saves there, and a hard link would make
    them bubble up into the original MO2 installation.

`session.py` orchestrates the `mo2` and `play` commands: prefix ready (T04) →
instance configured → launch → diagnostics.

### GameMode: launch wrapper, not installation

`environment/gamemode.py` wraps the command in `gamemoderun` when Feral
GameMode is installed. Three choices worth writing down:

- **Where**: only *game* launches (`launch_game`, `launch_flat`),
   never `launch_mo2` nor the installation steps — pinning the CPU governor to
   `performance` during a 146 GiB download has no benefit.
- **What to wrap**: `umu-run`, not the game executable. `gamemoderun` puts
   `libgamemodeauto.so.0` in `LD_PRELOAD`, which propagates to all descendants
   (umu runtime → wine → MO2 → the game); this is exactly the mechanism of the
   Steam option `gamemoderun %command%`. No need to go look for the game process
   at the bottom of the stack.
- **The trap of the `gamemode` group**: Fedora and Arch ship a polkit
   rule that reserves `cpugovctl`/`gpuclockctl` to members of the `gamemode`
   group (the action is in `allow_active: no`). Outside the group, the mode
   activates and `gamemoded -s` answers « active », but each governor change
   fails with `pkexec … Not authorized` in the log — nothing visible on the
   player side, half the benefit gone. `gamemode.group_status()` detects it and
   `doctor` shows the corresponding `usermod`. Membership is read from the system
   database (`grp`/`pwd`) and **not** from the process gids: that is what polkit's
   `subject.isInGroup()` does. Measured on 2026-08-13 on the dev machine — after
   `usermod -aG`, the governor switched to `performance` (16/16 CPU,
   `gamemoded -t` fully green) without re-login, even though the daemon and the
   calling shell dated from before the group addition.

Nothing is blocking: without GameMode, the command runs as-is; without the
group, the game still launches with I/O priorities.

**Expected noise in the launch log.** Every session, the output
contains dozens of lines:

```
gamemodeauto: dlopen failed - libgamemode.so: cannot open shared object file
```

It is cosmetic, and identical under Steam with `gamemoderun %command%`.
pressure-vessel does import the preloaded library into the steamrt
container (`--ld-preload=/run/host/lib64/libgamemodeauto.so.0:abi=x86_64…`, plus
its i386 equivalent), but **not** the `libgamemode.so.0` that it `dlopen`s
at runtime: it is not an `LD_PRELOAD` entry, and the container's linker does not
look in the host's `/usr`. Every internal process grumbles then refrains from
registering. No consequence: it is the `umu-run` process on the host that holds
the registration for the whole session. Verified on 2026-08-13, game launched:
`gamemode is active` and 16/16 CPU in `performance`. Same remark for the
`ERROR: Skipping ioprio on client […]` of the `gamemoded` log — chatty
upstream message, not a failure.

We do not filter these lines from our output: hiding what umu and wine spit out
would also hide the real problems the day there are any.

### Performance layers: MangoHud, vkBasalt (T20)

Two tools that Windows does not have, hooked into the **same entry point as
GameMode** (`environment/performance.py`, called by `process.run_detached`) and
therefore subject to the same boundary: `launch_game` and `launch_flat` only,
never `launch_mo2` nor the installation steps.

**Everything is off by default**, GameMode excepted. These layers change
rendering and performance: « nothing enabled » must remain a phrase a player can
write in an issue without having to verify it. GameMode, for its part, only
touches system priorities — it stays active by default, as since T02.

#### The nesting order, and why it is not free

```
gamemoderun umu-run ModOrganizer.exe 'moshortcut://:Anomaly (DX11)'
    + MANGOHUD=1 MANGOHUD_CONFIGFILE=… ENABLE_VKBASALT=1 VKBASALT_CONFIG_FILE=…
```

1. **`gamemoderun` in contact with `umu-run`.** It adds `libgamemodeauto.so.0`
   to `LD_PRELOAD` then execs the rest: it must stay in contact with the process
   that holds the game session.
2. **MangoHud and vkBasalt nowhere in the command.** These are implicit Vulkan
   layers: their manifest declares `enable_environment`, so a variable is
   enough. Their wrapper scripts would add one more `LD_PRELOAD` to a stack that
   already counts four, for a game that is Vulkan end to end (DXVK).

#### gamescope: proposed, then removed (2026-09-08)

The batch shipped a third tool, **gamescope + FSR**, outside everything (it is a
compositor). It was removed the very day of its first real session, and the
reason is worth writing down because it will come back on the table.

**What happened.** A session launched with `--gamescope -F fsr` on the dev
machine (Fedora 44, KDE Plasma 6 / KWin 6.7.4 on Wayland). gamescope starts,
selects the GPU, initializes its backend… then:

```
xdg_backend: Failed to dispatch input thread queue:
              protocol error 3 on xdg_surface@60
gamescopereaper: Parent of gamescopereaper was killed. Killing children.
```

`xdg_surface` error 3 = `unconfigured_buffer`: gamescope attached a buffer to its
surface before the host compositor had configured it. KWin applies the protocol
and kills the client. gamescope dies, its *reaper* kills all its descendants —
Xwayland, MO2, the game. **The session is lost, without warning.**

**What it is not.** Neither our composition nor our options: re-run identically
(`-W 1920 -H 1080 -F fsr --sharpness 2 -f`) with a Vulkan client going through
Xwayland, they work — swapchain created, 165 Hz, clean output —, including with
`MANGOHUD=1` and `ENABLE_VKBASALT=1`. The crash was not reproduced on demand: it
occurs in the **input thread** of gamescope, therefore probably on an interaction
or a window change, which a test client does not do.

**Why we remove rather than document.** This is a class of bug known upstream
(gamescope nested under a Wayland session;
[gamescope#1520](https://github.com/ValveSoftware/gamescope/issues/1520) describes
Proton games that crash gamescope). It does not arise on Steam Deck, where
gamescope *is* the session and not a nested client — that is, exactly the case
where FSR really serves. But we have no Deck to verify it, and a switch that
kills the session on the only testable machine is worse than no switch at all.
The decision is that of the project's user, made with knowledge of this tradeoff.

**What would be needed to reintroduce it** : a Deck (or a native gamescope
session) to verify the nominal case, and a launch-side guard that refuses
gamescope nested under a desktop Wayland session rather than letting the player
lose their session.

**A defect noted along the way, and which disappears with gamescope.** In the
log of this session, before even the game starts:

```
[MANGOHUD] process 'gamescope' is blacklisted in MangoHud
vkBasalt info:  config file: ~/.config/stalker-gamma-linux/vkBasalt.conf
```

MangoHud recognizes gamescope and backs off on its own; vkBasalt has no
blacklist and was therefore loading **into the compositor** in addition to the
game — our effects applied twice. Cause: `compose()` builds a single environment
for the whole process tree. If gamescope comes back one day, the Vulkan layer
variables will have to apply to the *internal* command
(`gamescope … -- env MANGOHUD=1 … gamemoderun umu-run …`), not to the whole thing.

#### The real risk: are these layers visible in the container ?

This is the question that had to be settled before writing a switch, because the
project already has a precedent: `libgamemodeauto.so.0` is indeed preloaded into
the steamrt container, but the `libgamemode.so.0` that it `dlopen`s afterwards is
not there — hence the dozens of `gamemodeauto: dlopen failed` documented just
above.

**What is established, and by what** (reading of the sources and upstream
documentation, on 2026-09-08) :

- the two manifests are implicit `GLOBAL`-type layers with `enable_environment`
  (`MangoHud` : `MANGOHUD=1` ; `vkBasalt` : `ENABLE_VKBASALT=1`) — so a variable
  is enough, there is nothing to preload ourselves;
- pressure-vessel **imports the Vulkan layers of the host** into the container
  (manifest *and* library, by ABI). This is what makes `MANGOHUD=1 %command%`
  work under Proton since the « soldier » runtime, and Valve's documentation
  reasons explicitly about vkBasalt *loaded into the container* (see « vkBasalt »
  below). The only known regression of this mechanism is specific to the
  **Steam Flatpak** ([steam-runtime#662](https://github.com/ValveSoftware/steam-runtime/issues/662)),
  where the imported folder came out of the loader's search paths;
- the home folder is **shared by default** with the container: our configuration
  files, written under `~/.config/stalker-gamma-linux/`, are visible there. For
  the case where `XDG_CONFIG_HOME` might point elsewhere, we add these paths to
  `PRESSURE_VESSEL_FILESYSTEMS_RO` — this is the remedy Valve documents, with
  `"$MANGOHUD_CONFIGFILE"` as an example. The variable is a `PATH`-style list: we
  **extend** the user's, we do not overwrite it;
- fundamental difference from the GameMode case: an implicit layer does not
  depend on a `dlopen` of a host library that the container would not have
  imported. It is the container's loader that reads the imported manifest and
  loads the imported library next to it. The failure mode of `libgamemode.so`
  therefore has no structural equivalent here.

**What was measured, and on what** (2026-09-08, dev machine: Fedora 44
KDE/Wayland, Ryzen 7 5700X3D, Radeon RX 7900 GRE (RADV NAVI31), umu 1.4.1,
GE-Proton11-6 → runtime **steamrt4**). The reasoning above is confirmed end to
end; the record, in the order it was done :

1. **pressure-vessel does import the host layers.** In the container,
   `/usr/lib/pressure-vessel/overrides/share/vulkan/implicit_layer.d/` contains
   the rewritten and renumbered manifests, **one per ABI** —
   `4-i386-linux-gnu.json` (`VK_LAYER_MANGOHUD_overlay_x86`) and
   `5-x86_64-linux-gnu.json` (`VK_LAYER_MANGOHUD_overlay_x86_64`) — whose
   `library_path` points to `/run/host/usr/lib/mangohud/libMangoHud.so` and
   `/run/host/usr/lib64/mangohud/libMangoHud.so`, both readable from the
   container. The `enable_environment` (`MANGOHUD=1`) is preserved on import.
2. **This is the only layer folder of the container.** It is designated by
   `VK_IMPLICIT_LAYER_PATH`, which pressure-vessel sets itself; the
   `/usr/share/vulkan/implicit_layer.d` of the container **does not exist**,
   `/etc/vulkan/implicit_layer.d` is empty, and `VK_LAYER_PATH` as well as
   `VK_ADD_LAYER_PATH` are absent. In other words, nothing from the host arrives
   by accident: what is there was imported deliberately.
3. **The loader does in fact load the layer.** With `MANGOHUD=1` and
   `VK_LOADER_DEBUG=layer`, inside the container :

   ```
   LAYER: Loading layer library /run/host/usr/lib64/mangohud/libMangoHud.so
   LAYER: Insert instance layer "VK_LAYER_MANGOHUD_overlay_x86_64"
   LAYER: This layer was enabled because Env Var MANGOHUD was set to Value 1
   ```

4. **And our configuration file is read.** `vkcube` launched in the container
   with `MANGOHUD_CONFIGFILE` pointing under
   `~/.config/stalker-gamma-linux/` produced the CSV log that this configuration
   asked for, whose header itself says where it comes from: `os = Steam Runtime 4`,
   `gpu = AMD Radeon RX 7900 GRE (RADV NAVI31)`,
   29 samples around 165–170 fps. The home folder is therefore shared, and
   `PRESSURE_VESSEL_FILESYSTEMS_RO` had nothing to catch.

**Consequence: the fallback `VK_ADD_LAYER_PATH` is not necessary** on this
configuration. We keep it documented below because it remains the lead if
someone hits the Flatpak regression cited above, but the nominal path is indeed
« an environment variable, and nothing else ».

**Expected noise, which we do not filter.** MangoHud active, the launch log
contains one line per measurement interval :

```
[MANGOHUD] [error] [cpu.cpp:786] Failed to initialize CPU power data
```

The container does not expose the RAPL counters (`/sys/class/powercap`): the
`cpu_power` column stays at 0, everything else is measured normally. Same course
of conduct as for the noise of umu and wine — we do not swallow it.

In-game record, the loop is closed (2026-09-08, GAMMA launched on the real
installation, GE-Proton11-6 / steamrt4). The process that renders the game is
`AnomalyDX11.exe`, an **ELF 64-bit** file. In its address space, live :

```
/run/host/usr/lib64/mangohud/libMangoHud.so     ← loaded
/run/host/usr/lib64/vkbasalt/libvkbasalt.so     ← loaded
```

Both come from `/run/host/`, that is, host layers imported by pressure-vessel:
the mechanism measured empty above behaves identically under DXVK and wine. Its
environment does carry `MANGOHUD=1`, `ENABLE_VKBASALT=1` and the two `…_CONFIG…`
pointing to **our** files, and vkBasalt announces itself what it read :

```
vkBasalt info:  config file: ~/.config/stalker-gamma-linux/vkBasalt.conf
vkBasalt info:  effects = cas:lut
vkBasalt info:  casSharpness = 0.4
vkBasalt info:  lutFile = ~/.config/stalker-gamma-linux/gamma-reshade-like.CUBE
vkBasalt info:  toggleKey = Home
```

No error: the LUT we generate is found and read from the container — this was
the last risk of the chain. Only message from MangoHud: `process 'explorer.exe'
is blacklisted`, which is the wanted behavior (no overlay on the wine shell,
only on the game).

**The four-step verification**, if the overlay does not show for someone :

1. `stalker-gamma-linux doctor` must show the three tools in `[OPTIONAL]`
   with, for MangoHud and vkBasalt, the **manifest path** found. No path = the
   layer is not installed where the loader looks for it, and nothing else will
   work;
2. `stalker-gamma-linux play --mangohud` : the launch log
   (`<root>/logs/mo2-game.log`) starts with the variables set
   (`# MANGOHUD=1`, `# MANGOHUD_CONFIGFILE=…`) then the command. If they are
   there and the overlay does not appear, the problem is **in** the container;
3. in that case, the next point to look at is the **ABI** (following paragraph);
4. if the ABI is right, add `VK_LOADER_DEBUG=layer` to the launch environment:
   the loader then says which manifests it read, from the game process' point of
   view — this is exactly record #3 above, to compare.

If the layers were definitely not imported (Flatpak case),
`PRESSURE_VESSEL_FILESYSTEMS_RO` (already set) plus `VK_ADD_LAYER_PATH` pointing
to `/usr/share/vulkan/implicit_layer.d` would be the lead — `VK_ADD_LAYER_PATH`
*adds* to the standard paths where `VK_LAYER_PATH` *replaces* them, which would
hide the container layers.

#### The right ABI, or nothing

A Vulkan layer is loaded into the process that creates the instance, and must
therefore exist in **its** ABI. MangoHud in fact installs a manifest per
architecture (`VK_LAYER_MANGOHUD_overlay_x86_64` and `…_x86_32`). According to
how the Proton build runs a 32-bit executable (32-bit unix layer, or « new »
WoW64 where the whole unix stage is 64-bit), it is one or the other that counts
— and it is not us who decide that. Hence :

- Arch: `lib32-mangohud` is part of the shown remedy, as `lib32-gamemode` for
  GameMode ;
- Fedora and Debian package the 32-bit variant under the same name but another
  architecture (`mangohud.i686`, `mangohud:i386`): impossible to announce as a
  simple package name — `apt` does not even know how to *query* `:i386` without
  `dpkg --add-architecture` — so it is a note attached to the remedy.

**The vkBasalt case, and why `doctor` no longer settles for the manifest.**
Observed for real on 2026-09-08. Fedora ships `vkBasalt.x86_64` and
`vkBasalt.i686` — two RPMs, **a single** manifest, whose `library_path` is
`/usr/$LIB/vkbasalt/libvkbasalt.so`. `$LIB` is a token that the linker replaces
with the directory of the process architecture. With only the 32-bit package
installed, the manifest was therefore present, `doctor` showed `[ OK ] vkBasalt`,
and the layer did not load: the game looks for `/usr/lib64/vkbasalt/`, which did
not exist. Measured in the container — `ENABLE_VKBASALT=1`, **zero** occurrences
of `VK_LAYER_VKBASALT`, and not a single line of warning. The failure mode is
strictly silent, which is the worst case for a cosmetic setting: nothing
distinguishes « the layer is off » from « the layer is broken ».

`environment.vulkan.layer_abi_support()` now handles this case: it goes through
**all** the manifests of the layer, expands `$LIB` over the known values
(`lib64` on Fedora/Arch, `lib/x86_64-linux-gnu` on Debian), and reads the
**ELF class** of the found file — it is that which designates the ABI, not the
directory name, which varies from one distribution to another. Three verdicts,
and the third counts as much as the others :

- `PRESENT` — a library of the game's ABI exists ;
- `MISSING` — libraries exist, none in the right ABI: `doctor` says so and gives
  the package to install ;
- `UNKNOWN` — unreadable manifest, or simple soname left to the linker
  (`libVkLayer_MESA_device_select.so`): we **say nothing**. Same rule as
  `checks._libunrar_version` — not knowing is not a reason to alarm.

The `MISSING` verdict stays in `OPTIONAL` and not in `MISSING` on the
`Requirement` side: these layers are cosmetic, and making `doctor` error out for
an absent overlay would be disproportionate. It is the displayed detail that
carries the nuance.

#### vkBasalt: the preset the README promised

The pipeline removes ReShade on every install and every update, and the README
offered vkBasalt « as an equivalent » without anything in the code providing it.
The delivered preset is `effects = cas:lut` : *Contrast Adaptive Sharpening*
sharpness (reason #1 for installing ReShade), then a color lookup table
**generated by us** — light S curve (contrast +18 %) and saturation gain (+8 %),
neutral at 0, 0.5 and 1.

Why a LUT `.CUBE` and not a ReShade `.fx` shader, which vkBasalt can nonetheless
run: a `.fx` requires `reshadeIncludePath`/`reshadeTexturePath`, so a
third-party shader repo installed somewhere — and Valve's documentation lists
exactly this trap, « vkBasalt crashes if you ask it for shaders that cannot be
found », the host's `/usr/share` not existing in the container
([steam-runtime#381](https://github.com/ValveSoftware/steam-runtime/issues/381)).
A LUT is a text file that we write in the home folder, whose generation is tested
without launching anything, and which cannot be missing since we produce it just
before the launch.

**Upstream is dead, and we keep it anyway — assumed decision.** Noted on
2026-09-08: the last commit of [vkBasalt](https://github.com/DadSchoorse/vkBasalt)
dates from **October 4, 2023**, the last release (`v0.3.2.10`) from July 3, 2023,
and its content was « fixed build with GCC 12 ». 80 open issues, nobody to close
them. On the Fedora side, the whole changelog since 2024 is only *mass rebuilds*
— no version bump in three years. To compare with the other two layers in the
batch: MangoHud is at 0.8.3~rc1 (January 2026).

We keep it for three reasons, in this order :

1. **it is the only packaged.** The whole `doctor` model rests on « here is the
   command for your distribution ». The natural successor,
   [vkShade](https://github.com/ralgar/vkShade) — rewritten from scratch,
   ReShade-compatible, actively developed — is in no repo and announces itself in
   **pre-alpha** (« expect bugs, incomplete features, and breaking changes »).
   Asking a player to compile a pre-alpha Vulkan layer is contrary to the reason
   for being of this project ;
2. **dormant is not broken.** It is a small layer against a retro-compatible
   Vulkan API; it is measured functional in the container, in game, on a 1.4
   loader (record above) ;
3. **replacing it will cost little.** `environment/vkbasalt.py` comes down to
   three things — a manifest name (`LAYER_STEM`), an activation variable
   (`ENABLE_VARIABLE`) and a configuration file. Switching to vkShade the day it
   is stable and packaged means rewriting this module, not the batch.

To watch, therefore: vkShade leaving pre-alpha **and** entering the repos. This
is the signal that will trigger the switch; until then, changing would be trading
something that works for something that compiles.

#### Our configuration files, never the user's

`~/.config/stalker-gamma-linux/mangohud.conf`, `vkBasalt.conf` and
`gamma-reshade-like.CUBE` are written by us, designated by `MANGOHUD_CONFIGFILE`
and `VKBASALT_CONFIG_FILE`, and **rewritten on every launch**: it is the setting
chosen in the preferences that counts, not the file content. Their header says
so to whoever opens them. The user's global configurations
(`~/.config/MangoHud/MangoHud.conf`, `~/.config/vkBasalt/vkBasalt.conf`) are
neither read nor modified: someone who has set their overlay for all their games
must not see it change because they checked a box on our side.

#### Log

The variables set by the layers are written at the head of the launch log
(`# MANGOHUD=1`, …) before the command line. This is the first question that must
be answerable when the overlay does not appear. Nothing is filtered, here as
elsewhere: the layer warnings — like those of umu and wine — stay in the log.

## CLI orchestrator (T07)

### Framework: `argparse`, not `click`/`typer`

Tasks T04-T06 had already laid down, command after command, a complete `argparse`
CLI (subcommands, `--help` per command, dispatch tested — 182 tests even before
T07). Reworking it in `click`/`typer` now would have been a pure rewrite (parser
+ ~180 dispatch tests) without functional gain: `argparse` already covers all the
acceptance criteria (subcommands, clear help, return codes). We therefore keep
it, and `rich`/`logging` (added in T07) provide readable progress and logs
regardless of the chosen parser.

### `install`: resumable pipeline

`orchestrator.run_install` now chains **six** steps (`anomaly`, `gamma`,
`reshade`, `prefix`, `mo2`, `shortcut` — the last only if `--shortcut`) on the
`--target` installation: the prerequisite check (`environment.report`) is only a
non-blocking warning at the head, the others delegate to the engine (T03), the
prefix (T04) and the MO2 instance (T05).

Each step is already idempotent **on the module side** (see above); `state.py`
adds on top a resume shortcut: a TOML under
`~/.config/stalker-gamma-linux/install-state.toml`, keyed by absolute target
path, marks each validée step. A re-run after Ctrl-C skips the steps already done
instead of re-playing them (in particular `full-install`, whose MD5 re-
verification on ~90 GB is not free). This is **not** the health source of truth
of the installation — if a step is broken manually afterwards, it is
`update`/`prefix-doctor --repair` that fixes it, not an automatic invalidation of
this state.

`run_update` (also in `orchestrator.py`) is simpler and non-resumable by design
(the prompt does not ask for it): `update_gamma` → removal of ReShade/purge
shaders → `verify` (check-anomaly + check-md5), on every call.

### `doctor`: composition, not merger

The `doctor` command (`doctor.py`, package root — distinct from
`environment.report` and `prefix.doctor`) shows the three existing reports side
by side (environment, prefix, installation state) without merging them. The
return code reflects only the system prerequisites: the prefix/installation can
legitimately be incomplete on a new machine before `install`, this is not a
failure of `doctor` — `prefix-doctor` remains the tool of truth for the health of
the prefix.

### Output and logs

`output.py` centralizes the output of the orchestrated commands (`install`,
`update`, `doctor`) via `rich.console.Console` (colors, formatting), and doubles
every message to the application logger (`logging_setup.py`). The latter configures
a always-active `RotatingFileHandler` (DEBUG) under
`~/.local/state/stalker-gamma-linux/`, and a console handler whose level follows
the global `--verbose` flag (before the subcommand:
`stalker-gamma-linux --verbose install`). The low-level modules (`engine/`,
`prefix/`, `mo2/`) keep their existing `print()`/`on_progress` — untouched,
already readable and already tested; only the orchestrator layer adds `rich`.
`cli.main()` catches any unexpected exception at the root, logs it with its full
traceback, and shows an actionable message (log path, `--verbose` suggestion)
rather than a raw traceback.

## GTK4/libadwaita GUI (T08)

### No business logic in the GUI: `output.Reporter` + existing callbacks

The GUI (`src/stalker_gamma_linux/gui/`) consumes exactly the same functions as
the CLI (`orchestrator.run_install`/`run_update`,
`mo2.session.run_mo2`/`run_play`, `doctor.build_full_report`) — nothing is
reimplemented. Two small additions, shared with the CLI and tested independently
of GTK, made this possible :

1. **`output.Reporter`** (structural protocol): `orchestrator.run_install`/
   `run_update` used to call `output.header`/`step`/`warn`/… hard-coded
   (`rich` + logger). They now accept `reporter: Reporter =
   output.console_reporter` — the CLI does not change behavior (the default is the
   old `output.py`), the GUI provides `gui.worker.QueueReporter`, which pushes
   each event onto a `queue.Queue` instead of printing it.
2. **`cancel_event: threading.Event | None`** : added to `engine.process.run`,
   `prefix.process.run_in_prefix`, and propagated through `engine/runner.py`,
   `prefix/provision.py`/`proton.py`/`verbs.py`/`download.py` and
   `orchestrator.run_install`/`run_update`. A dedicated « watchdog » thread
   (`_watch_cancellation`) kills the subprocess (`terminate` then `kill`) as soon
   as the event is raised; the subprocess then raises `EngineCancelledError`/
   `PrefixCancelledError` instead of the usual error code.
   `orchestrator.CANCELLED_EXIT_CODE` (130, POSIX convention 128+SIGINT) is
   returned in this case — the interrupted step is not marked done in `state.py`,
   a re-run plays it. Never passed through the CLI (`None` by default): unchanged
   behavior.

`mo2.session.run_mo2`/`run_play` were hard-wired to `print()`; they now accept
`on_progress: Callable[[str], None] | None` (falling back to `print` if absent,
resolved dynamically to stay monkeypatchable — see the late-binding trap below).
`doctor.py` was split: `build_full_report()` does the collection (returns a
`DoctorReport` structured, `Requirement` per `Requirement`, with `install_hint`);
`run_doctor()` (CLI) is the only function in the module that prints.

Trap encountered: `on_progress: ProgressCallback = print` as the *default value*
binds `print` to the module import — a test that monkeypatches `builtins.print`
later sees nothing. The fix (already in use elsewhere in the code,
`engine/process.py` etc.): `on_progress: ... | None = None` + `progress =
on_progress or print` **in the body** of the function, resolved on every call.

### Pure modules (`viewmodel`, `worker`, `prefs`, `phases`, `space`, `summary`,
`format`): testable without `gi`

`gui/__init__.py` is empty of any import: these modules never depend on PyGObject
and are tested by `pytest` like any other module of the project
(`tests/test_gui_*.py`), including on a machine without GTK4/libadwaita. Only
`gui/app.py`, `gui/theme/` and `gui/windows/*.py` import `gi`.

The « launcher » rendering (post-T08 overhaul) rests on six additional pure
modules, each with its test suite :

- **`phases.py`** : immutable timeline of install/update steps. Each
   `Reporter` event (`step`/`skip` indexed « n/total », `progress`,
   `error`, `success`) produces a **new** `Timeline`; the progress view only
   redraws it (states done / already done / en cours with engine detail /
   failure) and draws from it a **real fraction** — no more pulsating bar during
   an installation.
- **`space.py`** : free space on the volume of the target
   (`shutil.disk_usage` on the first existing ancestor), verdict
   OK / just / insufficient / unknown. The pre-installation dialog blocks
   under `MINIMUM_FREE_BYTES` (160 GiB) and warns under
   `RECOMMENDED_FREE_BYTES` (250 GiB, upstream recommendation). These two
   thresholds come from `sizing.py` (see « Disk sizing » below) — no local
   constant.
- **`summary.py`** : compresses the `EnvironmentReport` (7 prerequisites) into a
   chip « Système prêt / N prérequis manquants » for the home — the collection
   runs in a thread at startup and on every return from a task.
- **`format.py`** : parsing of « n/total » indices, sizes (`Gio`), durations, and
   the `UNKNOWN` constant (« — »): « je ne sais pas » must have *one* single
   appearance throughout the interface, and never be written « 0 ».
- **`stats.py`** : the figures of the home tiles — mods **active /
   installed** (« 579 / 728 ») and launcher version. The denominator comes from a
   single `scandir` on `<root>/gamma/mods` (no recursive descent: MO2 puts a
   folder per mod flat), the numerator from the `modlist.txt` of the
   `G.A.M.M.A` profile — this is the number Mod Organizer itself shows. The
   separators are excluded from both: they are real folders, but never active
   mods, and at the denominator they would make the fraction unreachable.
   Read in the same polling thread as the environment and disk space.
- **`jobs.py`** : the seven long tasks (install, update, verify, backup,
   restore, play, MO2) described outside GTK — title, function to launch in the
   thread, cancellability, step labels. Each `run` calls exactly the function
   that the corresponding CLI command calls; the point of the module is that
   these connections are verifiable without displaying a window.

### Visual identity: `gui/theme/`, and generated artwork

The visual identity lives in `gui/theme/` — no view does inline CSS: they lay
down classes (`deck`, `tile`, `console`, `phase-node`…) and `theme/style.css`
decides their rendering. Four decisions structure this file :

- **the CSS is a CSS file**, not a Python string. A 460-line sheet in a f-string
  forces doubling every brace and forbids any normal re-reading. It is declared
  in `package-data`: without this line, a `pip` installation would ship a GUI
  without style ;
- **one definition per color**, in `@define-color` at the head of the file — and
  not the GTK 4.16 CSS variables, the target remaining Ubuntu 24.04 (GTK 4.14,
  libadwaita 1.5) ;
- **nothing that costs much in software rendering**. The GUI forces
  `GSK_RENDERER=cairo` (cf. `gui/launch.py`), so short and few shadows, no blur
  computed at display ;
- **the keyboard focus stays visible everywhere**. A skin that erases it makes the
  application unusable without a mouse.

`theme.parse_errors()` reloads the sheet in a throwaway provider and returns the
syntax errors encountered: GTK, for its part, silently ignores a faulty
declaration, and a misspelled property was only visible to the eye on the screen
we had not reopened. A smoke-suite test requires it empty, and `install_theme()`
logs what it finds.

`theme.texture(name)` decodes an artwork **once for the whole application**
(`lru_cache`). Each page placed on the artwork previously loaded its own copy —
three decodings of the same JPEG and three textures of several MB, re-instantiated
on every navigation.

The artworks are generated deterministically by `scripts/generate_background.py`
(numpy + Pillow, fixed seed, never imported by the package), from the
`scripts/artwork/` package: `noise` (fBm, warped fBm, halos), `silhouettes` (the
visual vocabulary of the Zone — Duga antenna, reactor chimney, power lines, dead
trees, grass — traced by supersampling then reduced in BOX, a kernel with negative
lobes bordering the silhouettes with a light outline), `scene` (the composition
in successive planes, atmospheric perspective included) and `grade` (bloom,
bicolor shift, chromatic aberration, vignette, grain). Two files come out of it :

- `assets/background.jpg` — the home, where the artwork is the subject ;
- `assets/background-blur.jpg` — the content pages (progress, diagnostics), where
  it is only an ambiance behind text. Blurred and darkened **at generation** and
  at half resolution: readability no longer depends on a CSS veil, and there are
  four times fewer pixels to scale on every redraw.

`scripts/generate_social_preview.py` reuses the same `render_zone()`: the repo
card and the launcher window show the same landscape.

### Documentation screenshots

`scripts/capture_screenshots.py` regenerates `docs/screenshots/`. It redirects
the XDG variables to a temporary folder and builds a demonstration installation
(`/home/stalker/Games/GAMMA`): no screenshot publishes a real path. Each screen
is built for real, then rendered **off-screen** (`Gtk.WidgetPaintable` +
`Gsk.CairoRenderer`), without a system capture tool — the result is therefore the
same under KDE, GNOME or on a CI runner. The window must still be presented for
the duration of the rendering: GTK allocates and draws nothing until a widget is
mapped.

- **`viewmodel.py`** : `InstallStatus` (NOT_INSTALLED/INSTALLED) reads only
  `state.py` (local TOML, quasi-instant) — **not**
  `doctor.build_full_report`, which launches several subprocesses
  (`which`/`ldconfig`/`vulkaninfo`…) and would refresh the status of the main
  window by freezing the UI for the duration of these calls. The Diagnostic view,
  for its part, calls `build_full_report` in a dedicated thread.
- **`worker.BackgroundTask`** : launches `func(events, cancel_event) -> int`
  in a daemon thread; publishes `ReporterEvent`/`DoneEvent`/`FailedEvent` on a
  `queue.Queue`. The GTK side (`ProgressPage`) drains it via
  `GLib.timeout_add` (poll, 80 ms) — this is the only point of contact with the
  GTK loop, everything else in `worker.py` is pure `threading`/`queue`.
  The drainage is integral (taking an event out of the queue costs nothing), but
  the **rendering** is capped at `_POLL_EVENT_BUDGET` events per tick:
  gamma-launcher comes out in bursts of hundreds of lines, and rendering them all
  in a single loop turn froze the window (138 ms measured on a burst of 5000
  lines, 24 ms with the budget) — yet « Annuler » is the only control on this
  screen. The delay is picked up on subsequent ticks; a task end seen behind a
  burst is handled in the very tick it arrives, without waiting for the delay to
  display. The console is bounded to `_LOG_MAX_LINES` (the buffer would otherwise
  reach hundreds of thousands of lines on a complete install): the truncation
  concerns **only** the display, the complete log staying written to disk by
  `QueueReporter`.
- **`prefs.py`** : GUI preferences (installation path, Proton-GE version,
  creation of the shortcut) in TOML under
  `~/.config/stalker-gamma-linux/gui-prefs.toml` (reuses
  `state.config_dir()` — same XDG root as `install-state.toml`, separate file).
  « Version Proton-GE » needed a small shared addition (not GUI-only):
  `proton.ensure_proton(..., release=...)` /
  `provision.ensure_prefix(..., proton_release=...)` /
  `orchestrator.run_install(..., proton_release=...)`, empty = unchanged default
  behavior (latest GE release, decision T04).

### « Mise à jour disponible»: no detection, explicit action

The T08 prompt asked for a status « pas installé / installé / mise à jour disponible
». Verified in `gamma-launcher` (v3.1, `commands/install.py`) : there is
**no cheap way** to know if an update is available without launching the download
itself — the revision comparison (`crev == g.downloader.revision`) is done
*after* downloading the GitHub archive. Building a detection (e.g. calling an
external API) without a real mechanism behind it would have been business logic
invented in the GUI, contrary to the principle of the prompt. The status is
therefore binary (`InstallStatus`), and « Mettre à jour » is exposed as an
explicit action of the menu (always visible, enabled only if installed) rather
than as a third auto-detected state — exactly what the CLI already does with its
separate `install`/`update` commands.

### Cancellation

`ProgressPage` passes a fresh `threading.Event` per task to `BackgroundTask`; the
« Annuler » button raises it. Propagated to `orchestrator.run_install`/
`run_update` (see above), it cleanly interrupts the running subprocess — never a
`kill -9` of the GUI process itself. `mo2.session.run_mo2`/`run_play` do not
accept `cancel_event` (scope deliberately limited: these are short launches, not
downloads of several GB); the Annuler button of `ProgressPage` is therefore
hidden for these two tasks (`cancellable=False`).

### Steam Deck adaptive (1280×800)

Default window 820×620 (comfortable in 1280×800, including in borderless window of
Gaming Mode); main buttons sized for touch (`_BUTTON_HEIGHT = 56`, HIG
recommendation ≥ 44 px); keyboard/gamepad navigation free via the standard GTK4
focus (`set_default_widget` + initial focus on the context button, Steam Input
maps the D-Pad/A onto the arrows/Enter without specific code); native
touch-gesture back via `Adw.NavigationView`. No `Adw.Breakpoint`: 1280×800 is a
wide landscape, not a narrow collapse case — adding one would have been complexity
without a real identified need.

### Application identifier

`Gio.Application` requires an id syntactically D-Bus-like (at least one dot),
unlike the T06 `.desktop` which stays `stalker-gamma-linux` without reverse-DNS
(explicit decision of `desktop/paths.py`, to stay independent of a precise GitHub
account). Same logic repeated here: `org.stalkergammalinux.Gui` rather than
`io.github.<compte>...`. Static file `data/stalker-gamma-linux-gui.desktop`
(+ `data/icons/`) for the applications menu — installed by `install.sh`; it is
**not** auto-installed by `pip install`, unlike the dynamic shortcut of T06
(`stalker-gamma-linux shortcut`, which points to `play`, not to the GUI).

### Development environment: `--system-site-packages`

PyGObject has no manylinux wheel (extension linked to the system GLib/
GObject-introspection); `pip install pygobject` fails without
`cairo-devel`/`gobject-introspection-devel` (observed for real). The dev venv is
therefore created with `python3 -m venv --system-site-packages .venv` to see the
system PyGObject (already installed, GTK4 4.22 + libadwaita 1.9 validated for
real); `PyGObject-stubs` is added to the `dev` extra so that `mypy --strict`
types the `gi.repository.*` calls. The CLI never needs this group (`gui` in a
separate extra) — `stalker-gamma-linux-gui` (`gui/launch.py`) checks
GTK4/libadwaita before any `import gi` and shows an actionable message (per
distribution) if absent, instead of a raw `ModuleNotFoundError`.

## Integrity of installed mods (T12)

`engine.verify` (`check-md5` of the engine) answers « was the download correct »:
it compares the **archives** of `gamma/downloads` to the published sums. It says
nothing about what is actually placed on the disk. The `integrity/` package
covers the other half — « is the install still intact » — that is, the first
symptom a player reports (« the game has been crashing since yesterday », after
another tool overwrote a file or a full disk truncated one). Command
`verify [--repair]`, plus two buttons in the Diagnostic view of the GUI;
`integrity.run_verify` is the only entry point, shared word for word by both
(`Reporter` + `cancel_event`).

Seven decisions that are not read in the code :

1. **The reference is a text file next to the install** (`<install>/gamma-md5.txt`,
   `md5sum` format), not a state under `~/.config`. It describes *this*
   installation: it must follow it if it is moved or backed up, and stay
   human-readable. The parsing splits **after the hash** instead of truncating at
   offset 32: a file produced by `md5sum -b` (prefix `*`) or retabulated
   continues to be read, and any line that does not re-read is reported to the
   user — never swallowed, because it produces false « supprimé ».
2. **First pass = recording, not verification.** Without a prior reference there
   is nothing to compare; announcing « aucun écart » would suggest a verification.
   We record, we say so, and the reference re-take after repair is a **step in
   its own right** (a second complete scan, announced as such) — without it, the
   mods we just put back in state would show up as « modifiés » on the next pass.
3. **An interrupted scan cannot reach the writing of the reference.** This is not
   a calling convention: `scan.scan_tree` **raises** `IntegrityCancelledError`
   instead of returning a partial result. A potentially broken install cannot
   therefore be frozen as a new reference by a Ctrl-C or a Annuler button.
4. **« Coming from the modpack » is not read in a single file.** This is the trap
   that only a real install revealed: `full-install` populates `mods/` from
   **three** sources, and `modlist.txt` is only one of them.
   - `modlist.txt`, separators included — `mo2/modlist.py` excludes them for good
     reason for those who count mods, but gamma-launcher creates real folders with
     a `meta.ini` (`SeparatorInstaller.install`) : 28 on the test install ;
   - `modpack_addons/` — 388 folders delivered as-is, copied as-is by
     `_copy_gamma_modpack`, **absent from `modlist.txt`** ;
   - the Git resources (`gamma_large_files_v2`, `teivaz_anomaly_gunslinger`),
     whose folders are only known after cloning.

   We combine the first two, which are read offline. The third stays out of reach
   without plumbing Git: its mods fall into « source inconnue » and are reported
   then **left intact** — the right failure, the doubt must always prevent a
   deletion. On the test install, the number of unrecognized folders went from 43
   to 5, of which 3 fall under this last case; the message therefore no longer
   claims that the player added them.

   Measured corollary: since repair delegates to `full-install`, which
   re-extracts **all** the mods over the existing one, it is not limited to the
   targeted mod — 478 files of other mods changed, and 43 appeared, on a real
   install. Nothing disappeared, and the files added by the player were preserved
   (`copytree(dirs_exist_ok=True)` overwrites, does not delete). Useful side
   effect: the mods excluded from repair still see their damaged files restored in
   place. The command now says this explicitly rather than letting one believe in a
   strictly surgical operation.
5. **The `added` files are never repaired — and the folder that contains them is
   not either.** Repair is `rmtree` on the mod folder: a retouched `.ltx` or a
   patch placed inside would go with it. Sparing the file at diff time is
   therefore not enough, we must spare its folder. A damaged mod that contains
   additions is reported with its reason and left intact, like mods without
   upstream source (player extras). The authoritative list is the `modlist.txt` of
   `modpack_data/` placed by gamma-launcher, disabled entries included — disabled
   in MO2 does not mean absent from the disk.
6. **« Reinstalling this subset » does not exist on the engine side.**
   gamma-launcher v3.1 has no option to install only one mod
   (`FullInstall._install_mods` walks the whole list). What we control is the
   **re-downloaded** subset: by removing the mod folder *and* its archive, only
   these mods go back to the network, the rest being reused from the cache
   (`use_cached=True`). The folder → archive correspondence is read in the
   `meta.ini` that the engine writes at installation (`installationFile=`): this
   is the only one available **offline**, the real file name of a ModDB download
   being only known by querying the ModDB page.
7. **A file whose size and date have not moved is not re-read — and we say so.**
   The reference now carries a `taille,mtime_ns` column
   (`<md5>  <taille>,<mtime_ns>  <chemin>`), which allows `scan_tree` to re-take a
   fingerprint instead of reopening the file. Without it, two `verify` in a row
   re-read the 83 GiB identically — measured on a bench: 2.34 GiB go from 0.84 s
   to 0.04 s, no byte read, identical fingerprints. What it costs, said frankly: a
   corruption that would preserve size *and* date would become invisible. All
   those this module targets go through an ordinary write — truncation on a full
   disk, overwriting by another tool, interrupted extraction — and therefore move
   one or the other; what remains is the rewrite followed by a deliberate
   `os.utime` (an adversary's gesture, and this MD5 authenticates nothing — who
   can rewrite a mod can rewrite `gamma-md5.txt`, an unsigned text file) and the
   alteration occurring *under* the file system (bitrot, failing cable or RAM). It
   is for this last one that `verify --full` exists, which ignores the column and
   re-reads everything. Three guards make the default tenable: the number of files
   not re-read appears **in the report**, not in a footnote; a reference of old
   format has no column, therefore re-hashes everything (the doubt always forces
   re-reading, never the reverse); and the re-take that adds the column to such a
   reference attaches size and date only to files whose re-read fingerprint
   **equals** that of the reference — giving it to a damaged file would make it
   short-circuit on the next pass, and the fault would come out of the report
   without having been repaired.

Three implementation points that have a precise reason :

- **The progress is paced by elapsed time, never by index.** Mod files range from
  a few bytes to several gigabytes: an `i % 500 == 0` freezes the interface for
  long seconds on the big ones then drowns the console on the small ones. The
  counter is also refreshed *between two blocks* of the same file, and it is at
  the same place that cancellation is checked — a `cancel_event` raised in the
  middle of a 4 GiB file gives back control immediately. The clock is injectable,
  which makes the pace testable without `sleep`.
- **The hashing is parallel, the result is not.** `scan_tree` distributes the
  files over a `ThreadPoolExecutor` (never `multiprocessing` : `hashlib` releases
  the GIL, the serialization cost would eat the gain). Measured on 7.86 GiB and
  20,735 files, page cache emptied before each pass: 18.6 s before, 10.4 s after
  — the fingerprints being bit identical. Three precautions make this gain
  acceptable :
  - **The order does not move.** The tasks are consumed in the order of
    *submission* and not of completion, which leaves `digests` in the traversal
    order; `unreadable` is filtered at output, its entries arising both from the
    traversal and from the hashing, therefore at offset moments.
  - **The default adapts to the media.** Four threads on flash memory — this is
    the elbow of the curve, doubling only again yields ~8 % because the ceiling is
    no longer MD5 but the part of the loop that keeps the GIL — and **a single**
    one on a platter disk, where four concurrent readers replace a sequential read
    with a head seek back and forth. `integrity/storage.py` answers this question,
    and it cannot settle for `st_dev` : on btrfs or NFS the kernel returns an
    anonymous number, we have to go through `/proc/self/mountinfo` then
    `queue/rotational`. An undeterminable media is treated as non-mechanical.
  - **Cancellation stays immediate.** An internal `threading.Event` doubles that
    of the caller, who may be absent: Ctrl-C included, the threads in flight exit
    at the next block (~1 MB) instead of finishing a file of several GiB, and
    `scan_tree` never gives back control leaving a thread behind it.
- **The mod names are validated before any `rmtree`/`unlink`**, by the same
  functions as T11 (`paths_safety.validate_removable_child`) : they come from the
  upstream list and from `meta.ini`, not from us. A `..`, a path separator or a
  symbolic link makes everything refuse — and the refusal occurs **before** the
  least deletion, so that a dubious `meta.ini` does not leave a mod half removed.

### Side effect fixed along the way: `output.py` escaped `rich` markup

Messages passed to `output.progress`/`warn`/… were rendered as-is by
`rich.Console.print`, therefore interpreted as markup. A mod folder name like
`101- Mod A [pack]` — the brackets are common in the modpack — **disappeared**
from the display, and a string containing `[/…]` raised `MarkupError` in the
middle of an installation. The colors are now placed around an escaped message.
The escaping concerns only the console rendering: the logger and the GUI
`Reporter` always receive the raw message.

## Backup, restore, and modlist merge (T17)

This is G.A.M.M.A.'s #1 complaint, all platforms combined. The official wiki
writes it itself: « *every time you click Install / Update GAMMA, your modlist,
settings, and mod settings will reset. This is on purpose […] remember to make
backups before clicking that button* ». Under Windows, the answer therefore
comes down to advice nobody follows. Two halves, and they do not do the same
thing: the `backups/` package makes the loss **reversible**, the merge of
`mo2/modlist_merge.py` makes it **not happen**.

### Where savegames live — observed, not assumed

Anomaly is portable (`fsgame.ltx` : `$game_saves$ = $app_data_root$ |
savedgames\`), but under MO2 the USVFS can redirect these writes to `overwrite/`
or to the profile depending on the instance configuration. The question was
therefore settled **on the test install** before being coded
(`/mnt/games_samsung/Games/GAMMA`, GAMMA 920, MO2 2.5.2, recorded on 2026-09-07,
sessions played until August 26) :

| Observation | Measurement |
|---|---|
| `anomaly/appdata/savedgames/` | 29 files, 39 MiB, timestamped to the minute of the last game session |
| `gamma/overwrite/` | **empty** — created on August 22, never written |
| `profiles/G.A.M.M.A/settings.ini` | `LocalSaves=false`, and no `profiles/G.A.M.M.A/saves/` |
| last `usvfs-*.log` | **no** match for `savedgames` ; the only entries under `appdata\` concern `shaders_cache`, and they map the real path onto itself |

Conclusion: on the configuration livrée by GAMMA, the game writes its saves
**live** in `anomaly/appdata/savedgames`, without going through `overwrite/`. The
other two locations remain reachable by configuration (`LocalSaves=true` groups
sessions by profile; the USVFS would divert a write made in a virtualized folder
to `overwrite/`): they are therefore also backed up, when they exist and are not
empty. Three `is_dir()` against the risk of missing the real location, the choice
is quick. When two sets overlap (`gamma/overwrite/appdata/savedgames` lives under
`gamma/overwrite`), the larger wins — otherwise the backup would double in size
and the restore would have two truths.

### Format, rotation, restore

A timestamped folder per backup under `<root>/backups/`, **with the historical
naming** `profiles-%Y%m%d-%H%M%S`: the backups already placed by the old
`orchestrator.backup_mo2_profiles` thus remain recognized and restorable
(`manifest.legacy_manifest` synthesizes their manifest from what we know about
them with certainty — the folder *is* a copy of `profiles/`, and its name carries
the date). The prefix is therefore an assumed vestige: it is the **manifest**
(`backup.toml` : date, GAMMA version, sets, destinations, sizes) that says what is
inside, and it is that which `--list` reads, never a `stat` of the folder.

Three rules carry the rest :

1. **Rotation** — at most five automatic backups, the oldest goes beyond. A backup
   created explicitly (`stalker-gamma-linux backup`) never enters it: it is a
   return point, not a cache. Any deletion goes through
   `paths_safety.validate_removable_child` — it is an `rmtree` on a path derived
   from `--target`, exactly the perimeter of T11.
2. **Restore** — `restore <id>` backs up the current state **before** overwriting
   it (a failed restore must not be a one-way trip), refuses to run if MO2 or the
   game occupy the prefix (`prefix.session`, T13 ; `--force` overrides), and shows
   its plan with `--dry-run` like `uninstall` and `import`. Each destination is
   rebuilt **beside** then swapped by two `rename` : a copy failure leaves the
   player's folder intact, and a swap failure puts it back.
3. **What is put safely away before an `update`** — the profiles (the original
   motive: `full-install` rewrites them) **and the sessions**. The same update
   calls `purge-shader-cache`, therefore an upstream `rmtree` *in `appdata/`*,
   next to `savedgames/`; a few dozen MiB to cover the only player data that is
   not re-downloaded.

Verified on the real install on 2026-09-07: `backup --saves` produces a backup of
29 files/38.9 MiB, `restore` puts it back after setting the current state aside,
and the 29 files come out with the **same MD5** as before — including the one
that had been removed for the test. No swap residue (`.sgl-restore-tmp`/
`.sgl-restore-old`) behind.

### Three-way merge of `modlist.txt`

`full-install` rewrites `profiles/G.A.M.M.A/modlist.txt` with the upstream list
(`_install_modorganizer_profile` at gamma-launcher). Three distinct things
disappear: the mods **disabled** by the player, the **order** they adjusted, and
the mods they **added**. `mo2/modlist_merge.py` re-plays over the new upstream
list only the deviations attributable to it; `mo2/modlist_sync.py` is the disk
layer, and `update --no-merge` returns the historical behavior (upstream
overwrite + backup).

**Why a homemade snapshot, and not the `modlist.txt` of the modpack definition.**
The first reflex is to use
`gamma/.Grok's Modpack Installer/G.A.M.M.A/modpack_data/modlist.txt` as `base` :
it is there, it is upstream, it is free. Compared to the real profile of the test
install — 751 entries against 756, written the same day by the same
`full-install` — it differs by **27 entries**, of which a dozen are demonstrably
*not* player deviations :

- a sentinel `-End` (line 2) that MO2 does not take up ;
- a duplicate: `G.A.M.M.A. Vehicles in Darkscape` appears twice there ;
- two lines with trailing blank (`-G.A.M.M.A. FDDA Rework ` with a space,
  `+425- Dynamic News Manager Fixes and Tweaks - dEmergence` with a tabulation),
  that MO2 rewrites trimmed ;
- names that do not correspond to the folder actually placed under `mods/`
  (`272- Grulag's Dead Bushes - Grulag` against `Grulag's Dead Bushes`), and at
  least one upstream typo corrected along the way (`DarkasleQif's` →
  `Darkasleif's`).

Using it as `base` would therefore invent a dozen false « player additions » and
as many false deletions. We record **our own snapshot** (`<root>/backups/
upstream-modlist.txt`), taken just after the engine wrote the profile — at the
end of the `gamma` step of an `install`, and on every `update`. Assumed
consequence: on an installation that has never seen this version of the tool, the
first update does not merge, it records the reference, and says so.

**Order and state are two separate problems.** Order is a sequence of names,
state (`+` active, `-` disabled, `*` unmanaged) a property of each name. Mixing
them produces the subtly wrong merges that this task exists to avoid — a mod
moved *and* disabled is not twice the same deviation.

- **Order** goes through a classic diff3 on the sequence of names: region the
  player did not touch → upstream; region upstream did not touch → the player;
  **region modified on both sides → upstream**, and we say so.
- **State** is decided name by name: if the player changed it since `base`, it is
  theirs; otherwise it is that of upstream, which may have legitimately activated
  or disabled a mod in the new version. The whole marker is taken back, not only
  « active/disabled »: turning a `*` into a `+` would change the meaning of the
  line.

Five rules that are not obvious, and that the code applies :

1. `modlist.txt` is read **from bottom to top** (increasing priority towards the
   top). Reasoning « line N » gets the direction wrong half the time: nothing is
   indexed in absolute terms here, everything is positioned relative to
   **named neighbors**.
2. A mod **removed upstream** is never resurrected — its folder no longer exists
   under `mods/`, MO2 would show it as « missing ». The set of names of the result
   is constrained to `theirs ∪ (ours − base)`, and nothing else; if diff3 cannot
   hold this constraint, we fall back on the upstream order, which is complete by
   construction.
3. A mod **added by the player** is reinserted next to its closest preserved
   neighbor (we move away one notch at a time, looking first above), never stacked
   at the end of the list. An addition already repositioned becomes itself an
   anchoring: a cluster of mods added together keeps its internal order — the real
   case of the top of the list of a GAMMA install.
4. The **separators** are entries like the others — this is what makes a
   reinserted mod fall back in the right section — but are not counted as mods in
   the report.
5. **In case of doubt, we do not merge** : empty list, same mod twice,
   incomprehensible line → we keep upstream, we keep the backup, and we announce
   it. A silently wrong merge is worse than a manual restore.

After merge, the report says what was re-applied (« N mods reactivated/disabled
according to your settings, M mods added by you reinserted, K entries removed
upstream not restored »). Without this report, the user does not know whether to
open MO2 to check.

**Line endings.** The MO2 instance comes from Windows: the `modlist.txt` of the
test install is in CRLF. `Path.read_text` applies the universal newline
translation and would return a text in LF — the rewritten file would then change
line encoding from end to end without anyone asking for it. Hence
`open(..., newline="")` in read **and** write, and a always-atomic write (sibling
file then `os.replace`) : a cut in the middle leaves the old file intact, never a
truncated `modlist.txt` that would start MO2 with no mods.

Validated offline on the real list (756 entries, CRLF): the player's settings
return, their additions find their position, the mod removed upstream is not
resurrected, no duplicate, and the file stays entirely in CRLF.

## Session post-mortem (T18)

The post-launch diagnostic existed since T05/T14, but since `play` returns control
without waiting (T15), **no one called it anymore** : at the moment `play`
returns, the game is still running and the logs have nothing to say. T18 adds the
command that re-reads them when they finally have something to tell, and the half
that was missing — the X-Ray engine log, the only place where a GAMMA crash is
attributed to a mod.

The records that ground each marker (real location of the log, false-positive
measurements, provenance of the patterns) are in
`docs/MO2-PROTON-COMPAT.md` § « Session post-mortem » — they belong to the
document that already serves as reference for the diagnostic, not to this one.

### Command name: `postmortem`

« Post-mortem » is jargon, and the player's question is « why did it crash ? ».
The command keeps this name nonetheless, for two reasons :

1. the CLI of this project names **tools**, in English, and already on this
   register: `doctor`, `prefix-doctor`, `verify`, `import`. A `why-did-it-crash`
   command would stand out, and `crash` would lie — the command also serves to say
   « nothing broken » ;
2. the surface made for the player is not the CLI: it is the button
   **« Le jeu a planté ? »** of the main window, which appears only on the return
   of a `play` — the exact moment when it is sought. The technical name stays on
   the technical side.

### Breakdown

`postmortem/` package, one file per question :

| Module | Question |
|---|---|
| `markers.py` | What does a crash look like in an X-Ray log? (patterns + provenance) |
| `logfile.py` | Where is the log, and how to read it without loading it? |
| `outcome.py` | How did this session end? |
| `attribution.py` | Which mod provides the file named in the traceback? |
| `result.py` | The verdict and its pieces of evidence |
| `analysis.py` | Which diagnostic wins? |
| `report.py` | How to say it without asserting more than we read? |
| `session.py` | The CLI command |

### A single main diagnostic, and how we settle it

Priority order, from most upstream to most downstream :

    launch failure > lack of memory > engine crash > dead USVFS > normal session

Same rule as in T14: a user to whom three problems are announced fixes none of
them. A measured exception adds to it — two of the launch-failure markers are
**not fatal** (Proton writes `Prefix has an invalid version?!` then launches the
game anyway, measured in T16). Applied mechanically, the order would hide a real
crash behind a « rebuild your prefix ». The fact that settles it is not read in a
message but in the **modification dates** of the two logs: if the engine one dates
from another session, it does not describe this launch
(`analysis.describes_same_session`).

### Bounded read, from both ends

An X-Ray log is several megabytes and nothing bounds its size. The header
(`Game started:`, `'xrCore' build`) fits in the first kilobytes; the verdict and
the traceback are at the end, reached by `seek` then bounded `deque` — not by
re-reading the whole file to reach its end. Cost measured on the real install
(5.2 MB, 761 mods) : **0.02 s**, attribution included.

### Nothing is re-attributed twice

`integrity.report.mod_of` is already the only place that decides which mod a path
under `mods/` belongs to; `attribution.py` calls it instead of re-reading the
folder name, so the two never diverge. What this module adds — and which existed
nowhere — is the translation « engine resource name » (a *visual* without
extension, a bare script in a Lua traceback) to the plausible path under
`gamedata/`. The attribution does not walk the mod tree (hundreds of thousands of
files): it builds a few paths per mod and tests their existence, the
case-insensitive resolution only attempted in a second pass.

## Entry into the Steam library (T19)

T06 had set aside the writing of `shortcuts.vdf` and sent the user to
*Steam → Ajouter un jeu non-Steam*. This workaround **does not execute where it
serves most** : in Gaming mode (Steam Deck, Bazzite, SteamOS), you have to go back
to Desktop mode to do it. The technical reservations of T06 held, though: they
became the specification below rather than a reason to give up.

### The format, recorded and not assumed

No public specification exists. The codec (`steam/vdf.py`) was written against a
real `shortcuts.vdf` of the development machine: sequence of typed fields
(`0x00` map, `0x01` string, `0x02` signed 32-bit integer, `0x08` end of block).
The criterion that validates it is not « it re-reads » but **the byte-by-byte
round-trip** : reading then rewriting an unmodified file must return the same
bytes. This real file, anonymized by substitution of bytes of the same length, is
versioned in `tests/data/shortcuts-real.vdf` — a hand-made file would have proven
only our own understanding.

Three consequences in the code: `VdfOpaque` keeps verbatim every typed field we
cannot interpret; the `trailer` of the document keeps the tail of the file as-is
(the real file ends with four `0x08` — three block closures and a document
terminator); the strings are decoded in `surrogateescape`, so that a badly encoded
shortcut name survives instead of being « repaired ». A byte of unknown type, for
its part, is **refused** (`VdfFormatError` with its offset): guessing the length of
a field would make everything that follows unreadable, in a file we are about to
rewrite.

### The `appid`: what was verified

The formulas floating around (`crc32(Exe + AppName) | 0x80000000`, with or without
the quotes, signed or not) **do not reproduce** the identifier of the real file.
`logs/console_log.txt` says why: `sanitize shortcut app id "<exe>": replacing 0
with 3379557880, reason: k_unAppIdInvalid`. Steam does not apply a formula — it
**replaces an invalid identifier (0)** with a value of its choosing, and never
recalculates that of an existing entry (that of the real file survived a move of
the executable).

Hence the rule: **we write our own valid identifier** and name the artwork after
it; when an entry already exists, we **take theirs**. Leaving the field at 0 for
Steam to choose would be the real gamble — the value would be unpredictable and
the artwork placed in advance would match nothing. The value retained for a new
entry is the historical CRC32, not because Steam would share it, but because we
need one and it must be deterministic (recreating the shortcut must fall back on
the artwork already placed). The VDF stores a **signed** integer, the artwork file
names use the **unsigned** form of the same 32 bits: the two conversions live in
`steam/appid.py`, and nowhere else.

### Recognizing our entry: the `Exe`, not the name

The user can rename a shortcut in Steam; they cannot change the executable it
points to without making it something else. `steam/entry.py` therefore recognizes
our entry by its `Exe` (the console script of the package, whatever the venv).
Wanted effect: **the entry created by hand via *Ajouter un jeu non-Steam* — the
manipulation T06 recommended — is recognized as ours and updated, not duplicated.
As with `ModOrganizer.ini` in `mo2/ini.py`, only the keys we have are rewritten:
everything else — the Steam fields, those of the other shortcuts — comes out in
its place, with its original type and case.

### What protects the user's file

`shortcuts.vdf` contains *the other* non-Steam shortcuts, which nothing will
re-download. Same requirement as in T17: timestamped `.bak` copy before writing,
atomic write (temporary file then `os.replace`), never a partial rewrite. And an
upstream refusal: **Steam open = we do not write** — it keeps the file in memory
and rewrites it on leaving, so writing while it runs loses the work *without
message*. The detection (`steam/running.py`) follows the scheme of
`prefix/session.py` : `/proc` first, `pgrep -x` as fallback, and the kernel task
name rather than the command line — a `pgrep -f steam` would match our own process
and always refuse to write.

### Multi-accounts: we write for all

Shortcuts live per account (`userdata/<id>/config/shortcuts.vdf`), and native
Steam as well as Steam Flatpak can coexist. Guessing « the right » account from
the modification dates is a heuristic that is wrong on a shared machine; asking is
impossible where it counts — in Gaming mode, there is no terminal to answer. We
therefore write for **all** the accounts found: the gesture is reversible, and its
cost at a neighbor is one more entry in their library. The candidate roots are
deduplicated by **resolved** path (`~/.steam/steam` is a link to
`~/.local/share/Steam` : without this we would write three times in the same file,
two of them over the backup we had just taken.

Steam Flatpak is served like the others, with two adjustments: the absolute paths
written in the VDF are retranslated into the sandbox view (`~/.var/app/<id>/` y
**is** `~/`), and the user is warned that the launch, for its part, can fail from
this sandbox — the entry and the artwork, for their part, are correct.

### Artwork: only ours, pre-generated

The five files placed in `userdata/<id>/config/grid/` (`<appid>p.png`,
`<appid>.png`, `<appid>_hero.png`, `<appid>_logo.png`, `<appid>_icon.png`) all come
from the package. The three capsules are rendered offline by
`scripts/generate_steam_artwork.py` — same procedural engine as the background of
the GUI — then delivered as assets: the composition requires Pillow + numpy, which
are **development** dependencies, whereas the installed package must have nothing
to re-compose. No download, SteamGridDB included. On removal, a file whose bytes
are no longer ours (the user has put their own capsule there) is **left in place**
and reported.

### Two Steam notions, two settings

`prefs.create_steam_shortcut` already designated something else: an additional
`.desktop` entry that jumps straight into `play`, useful *as a target* for the
native Steam button. The name promised what T19 delivers. It is therefore renamed
`create_direct_shortcut`, and `add_to_steam` designates the entry in the library;
the old key of the preferences file stays read, so as to not silently reset the
user's choice to zero.

On the pipeline side, `steam` joins `shortcut` in `state.OPTIONAL_STEPS` : two
steps that `install` plays only if asked, and whose absence does not make an
installation incomplete. The « n/total » numbering now comes from
`state.planned_steps`, read both by the orchestrator and by the GUI progress bar —
the `STEPS[:-1]` that the GUI copied descending broke as soon as a second optional
step appeared.

## ModDB resilience: download failure, manual deposit (T22)

This is what breaks an installation for everyone, and upstream responds badly to
it — raw Python traceback, hard stop, no indication of what to do. The upstream
issues document it: #282 (Cloudflare captcha, open), #286 (`ModDBDownloadError`,
direct link 403 from the browser), #283/#284
(`AttributeError: 'NoneType' object has no attribute 'unpackinfo'` — an expired
ModDB link, not a corruption). We already knew how to handle this wall **on one
side** : `engine.runner.verify` classifies these markers as warning, not failure,
since `a3903dd`. This module carries the same reasoning on the path of the
**download**, where gamma-launcher, for its part, does indeed fail (non-zero code)
— a nuance we must never erase: a mod missing during an install is missing, this
is not a « maybe » like for `verify`.

**A single table of markers, not two that diverge.** Before `engine/ markers.py`,
`engine.runner._UNVERIFIABLE_MARKERS` and `engine.errors._MODDB_MARKERS` each
maintained their list, and « Download link not found when requesting » ended up
duplicated in both — a fix in one could silently diverge from the other.
`engine.markers.classify()` is the unique source, used as-is by `verify()`
(contract unchanged: `UNVERIFIABLE_MARKERS` remains exactly the old table, no
network marker added to it without that being asked for) and by `engine.errors`
(actionable instruction during an install).

**Three causes, read in the source of gamma-launcher v3.1 and not guessed**
(`launcher/mods/downloader/base.py`, `moddb.py`,
`launcher/commands/check.py` — tag studied in `docs/ARCHITECTURE.md`
« Engine integration ») :

1. **Network/ModDB unreachable** (`requests.exceptions.ConnectionError`, raised by
   `tenacity` only after 3 internal attempts spaced 30 s apart) — nothing to do
   with a specific mod, waiting is the only sensible remedy.
2. **Link of a mod broken or moved upstream** (`ModDBDownloadError`,
   « Could not find Filename/archive hash in », « No Info URL provided ») — manual
   deposit. A dead mirror, a mod removed from the site, and a Cloudflare challenge
   produce **the same text** on the `moddb.py::_get_download_url` side: the page
   answered (otherwise we would be in cause 1), but what we were looking for is no
   longer there. Indistinguishable from here, hence the same instruction for the
   three — this is not a gap, it is what the upstream code itself says. The
   `AttributeError` on `unpackinfo` (py7zr) is its indirect symptom:
   `mod.download()` records without checking the content of what ModDB returned
   (a new file is hashed only on the next re-run, `DefaultDownloader.download`), so
   a 147-byte HTML error page ends up saved under the expected `.7z` name, and the
   extraction crashes later on an archive that is not one.

**The mod name is not read in `output_tail`.** `engine.process.run` keeps only the
last 20 lines of output for the error message; the line
`[+] Processing mod {name} ({i}/{n})` (`launcher/commands/install.py:_install_mods`,
the only trace of the mod en cours in the whole flow) can be pushed out by a long
traceback — the real case of `AttributeError` on `unpackinfo` is ~21 lines by
itself. `engine.runner._install` therefore wraps `anomaly-install`/`full-install`
in a tracking that sees **all** the flow as it happens, retains the last mod and
the last announced files (`Calculating hash of {file}: `, printed by
`launcher/hash.py:check_hash` just before a cached archive is (re)verified), and
attaches them to `EngineExecutionError` if it ends up raising — without this, the
message could name the URL without ever naming the mod.

**`--retry-failed` reuses `integrity.repair`, it reinvents nothing.**
`orchestrator.run_retry_failed` removes the folder and the cached archive of only
the mods recorded in failure (`state.record_failure`/`load_failures`, same TOML
file as the pipeline progression), then re-runs `full-install` — exactly the
mechanism already used by `verify --repair` (T12). Same measured reserve as back
then, and for the same reason: gamma-launcher v3.1 has **no** option to only
re-play a subset of mods (`_install_mods` walks the whole list, without the per-
mod guard that `CheckMD5.run()` has, itself — see below); what we control is the
**re-downloaded** subset, the rest being reused from the cache (`use_cached=True`).
`install --retry-failed` can therefore, like `verify --repair`, update other mods
along the way — this is not a strictly surgical operation.

**The file deposited by hand is verified before touching anything**, when an
expected MD5 is known (`state.FailedMod.expected_md5`) : a deposit that does not
match is refused with a clear message (`engine.errors.DepositMismatchError`)
rather than left to the engine, which would re-download in silence without ever
saying so (`ModDBDownloader.download()` re-resolves the ModDB page systematically
before consulting the cache — see `_check_deposited_files`). In practice the
expected MD5 is rarely known: nothing in the current output of gamma-launcher
prints it (`_parse_moddb_metadata` keeps it for itself) — `engine.runner.
_MD5_HINT_RE` is a best-effort net for a future upstream version that would print
it, not a guarantee.

**An install cannot skip a broken mod and continue — we do not claim the
opposite.** `launcher/commands/install.py:_install_mods` has no per-mod `try`/
`except` : the first exception stops the whole pipeline (non-zero return code),
unlike `CheckMD5.run()` (`launcher/commands/check.py`), which absorbs
`HashError`/`ModDBDownloadError` mod by mod and only fails at the end — it is
precisely for this reason that `verify` can accumulate several « unverifiable »
entries in a single pass, when `install`/`update` can record **only a single** new
failure per execution. The « final report » (`state.format_failures`, shown at the
end of `install`/`update`/`--retry-failed`, including on a success if old failures
still linger) is therefore honest about this limit rather than claiming a count we
do not have: it lists what is *currently* recorded in failure, not a total
« X installed / Y failed » that no gamma-launcher command can produce for
`full-install`.

**What we do not do, deliberately.** No captcha workaround, no browser simulation
(Playwright, Marionette…), no unofficial mirror — the path explored by the fork
cited in #282. This is an assumed limit of the project, not an oversight: the user
has the right to download the file from their own browser, which we neither can nor
should do in their place. When the ModDB wall comes back too often for a given mod
(a page really removed, as in #283/#284), the right address is an upstream issue
(`https://github.com/Mord3rca/gamma-launcher/issues`, suggested in the message),
not a local fix that would hide the problem.

## Disk sizing (`sizing.py`)

The volume an installation requires is a **unique** datum, in
`src/stalker_gamma_linux/sizing.py` : breakdown (17 GiB of base game + 83 GiB of
modpack + 46 GiB of cache = 146 GiB, measured in docs/INSTALL-MANUAL.md §1),
blocking threshold (160 GiB, the total plus the extraction margin) and upstream
recommendation (250 GiB).

Why a dedicated module rather than local constants: the two consumers — the
« Disk space » line of `doctor` (`environment/checks.py`) and the pre-installation
dialog of the GUI (`gui/space.py`) — had diverged. `checks.py` took back the
upstream figure « 27 GB downloaded / 76 GB installed », which our own manual
invalidates (we **keep** the cache for incremental updates), while the GUI blocked
under 160 GiB. Result: at 120 GiB free, `doctor` showed « [ OK ] Disk space »
while the GUI refused to launch the installation. `tests/test_sizing.py` locks
this agreement threshold by threshold.

Unit: everything is in **GiB** (2³⁰ bytes), which `shutil.disk_usage` returns and
which the CLI as well as the GUI show — `gui/format.format_gib` labeled « GB »
values that were already GiB.

## Packaging: Flatpak/AppImage removed (2026-07-26)

T09 (2026-07-23) delivered two channels: a **Flatpak** (GUI+CLI, sandboxed) and an
**AppImage** (portable CLI). Removed from the project on 2026-07-26: dogfooding in
a VM and on Florian's real machine showed that the sandbox was constantly fighting
against the Wine/Proton nature of the tool (host tools invisible behind
`flatpak-spawn`, libunrar to rebundle, 32-bit stack missing on the GNOME runtime
side — spam of `pressure-vessel` crash notifications), whereas the **native**
install (`install.sh`, venv `--system-site-packages`) uses directly the
Wine/Proton/Steam/libunrar that the user already has on their machine. Only the
native channel remains; see « Development environment » below and `install.sh` at
the root for the current mechanism.

## CI (T10)

Three workflows (`ci.yml`, `upstream-watch.yml`, `release.yml`), details and traps
encountered in `docs/CI.md`. A structuring point: `ci.yml` and `release.yml` must
install GTK4/libadwaita system headers (`libcairo2-dev`, `libgirepository-2.0-dev`,
`gir1.2-gtk-4.0`, `gir1.2-adw-1`) before `pip install ".[dev]"`, even though the
CLI never needs GTK — the `dev` extra ships `PyGObject-stubs`, which pulls
`PyGObject` as a hard dependency (no manylinux wheel, same constraint as above
« Development environment »), so any installation of the `dev` extra on a bare
machine fails to compile without these headers.

`upstream-watch.yml` relies on a real asymmetry between the two upstream repos:
`Grokitach/Stalker_GAMMA` publishes neither tags nor releases (verified via the
API), followed by commit sha; `Mord3rca/gamma-launcher` publishes real Releases,
followed normally. The integration job runs in a `ubuntu:24.04` container (not the
bare runner) because `read_mod_maker`/the archive extraction of gamma-launcher
import `unrar` (ctypes) on load, which requires `libunrar.so` — absent from
`python:*-slim` images (Debian), present by default on Ubuntu (`multiverse`).

## Internationalization

All strings visible to the user (CLI, GUI, error messages of the shared business
modules) are in **English in the source code** (`msgid` gettext) and go through
`stalker_gamma_linux.i18n._()`. English is **the default language**, end —
deliberately no follow-up of the system locale (`LANG`/`LC_ALL`/`LC_MESSAGES`) :
otherwise a machine in `fr_FR.UTF-8` would display French without the user having
asked for it, which is not the wanted behavior here. Only the GNU `LANGUAGE`
variable, explicitly set, changes the language (e.g. `LANGUAGE=fr
stalker-gamma-linux doctor`) ; `gettext.translation(..., fallback=True)` returns
the `msgid` (hence English) as-is as soon as no requested language has a
corresponding `.mo`. Resolved **once** on the module import (classic gettext model:
changing language en cours de session requires a restart, never a bug).

Available translations: `src/stalker_gamma_linux/locale/<code>/LC_MESSAGES/
stalker-gamma-linux.po` (+ compiled `.mo`, shipped to the package via
`package-data`). French provided 100 % at the i18n overhaul (2026-07-26, 226
strings). **Babel** tooling (`dev` extra, pure pip — no system `gettext`/
`xgettext` dependency, consistent with the rest of the project which never requires
sudo) :

```sh
make extract-messages   # régénère le .pot depuis tous les `_("...")` de src/
make update-messages    # fusionne les nouveaux msgids dans chaque .po existant
make compile-messages   # .po → .mo, à refaire avant de tester une traduction
```

Adding a language: `pybabel init -i src/stalker_gamma_linux/locale/
stalker-gamma-linux.pot -d src/stalker_gamma_linux/locale -l <code> -D
stalker-gamma-linux`, translate the generated `.po`, then `make compile-messages`.

Test trap: the `pytest` assertions are on the English text (source), which must
not depend on the locale of the machine running the suite (e.g. development machine
in `fr_FR.UTF-8`). `tests/conftest.py` sets `LANGUAGE=en` **at module level** (not
in a fixture) : `i18n.py` resolves its translation only once, on the first import —
a fixture, even `autouse`, runs after this import and would come too late.

Outside the gettext perimeter (left as-is, these are not translatable strings):
the internal identifiers (`STEPS`, values of the `Status` enum, `INSTALL_COMMANDS`
keys) are never displayed directly — a separate mapping dict handles them each
time — and `gui/theme/style.css` (code comments, not user text).

## References

- Engine: https://github.com/Mord3rca/gamma-launcher
- MO2 × Proton × USVFS compatibility: `docs/MO2-PROTON-COMPAT.md`
- Modpack: https://github.com/Grokitach/Stalker_GAMMA (AGPL-3.0)
- Modlist API: https://stalker-gamma.com/api/list
- Historical guide: https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Manual install gist: https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
