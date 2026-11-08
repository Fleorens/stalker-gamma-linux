# Roadmap

Split into executable tasks: see [../tasks/](../tasks/).

## Phase 0 — Foundations ✅ (this commit)
- Repo, GPL-3.0 licence, architecture, task breakdown.

## Phase 1 — MVP: one-command installation
- **T01** Spec: manual install reproduced and documented (the reference).
- **T02** Python skeleton + environment/prerequisites detection.
- **T03** Wrapper around the gamma-launcher engine (install/update/check-md5).
- **T04** Proton prefix management (Proton-GE, umu, winetricks verbs).
- **T05** ✅ **tested for real (2026-07-22, GE-Proton11-1)** MO2 under Proton:
  auto config of the instance (`gamePath`/profile), launching the game via
  `moshortcut://` (USVFS, 577 mods served), USVFS diagnostics, flat fallback
  explicit, compatibility matrix (`docs/MO2-PROTON-COMPAT.md`).
  `mo2` and `play` commands.
- **T07** ✅ complete CLI orchestrator: `install` (resumable pipeline —
  anomaly → GAMMA → ReShade removal → prefix → MO2 instance → optional
  shortcut), `update` (modpack + MD5 re-verification), `doctor` (environment
  + prefix + install state), `play`/`mo2` (T05), `shortcut` (T06),
  `--verbose` + rotating logs + `rich` output, curl-able `install.sh`.

MVP deliverable reached: `stalker-gamma-linux install` → GAMMA playable via MO2
under Proton, resume after interruption, incremental update.

## Phase 2 — Desktop integration
- **T06** Desktop shortcut: `.desktop` entry + icon (the add to Steam was
  then left to the user, via the native button — a decision reopened and
  resolved the other way by T19).
- **T08** ✅ GTK4/libadwaita GUI, tested for real (2026-07-23): main
  window (status, context Install/Play button, Open MO2), progress
  view (step, bar, collapsible log, clean cancel), Diagnostic view
  (graphical rendering of `doctor`, copyable remedy commands),
  Preferences (path, Proton-GE version, Steam shortcut). Long-running
  operations off the GTK thread (`gui.worker.BackgroundTask`); no business
  logic in the GUI — same `orchestrator`/`mo2.session` as the CLI, via
  `output.Reporter` (new) and the `on_progress`/`cancel_event` callbacks
  already in place. `stalker-gamma-linux-gui` entry + `.desktop` + icon.

## Phase 3 — Distribution
- **T09** Flatpak packaging (main channel, sandboxed, Steam Deck included) and
  AppImage (portable CLI) implemented (2026-07-23, AUR removed from scope).
  **Removed from the project on 2026-07-26**: dogfooding (see T08) showed that
  the sandbox was permanently at odds with the Wine/Proton nature of
  the tool (invisible host tools, libunrar, 32-bit stack) while the native
  install (`install.sh`) directly uses what the user already has.
  Only the native channel remains.
- **T10** ✅ CI: `ci.yml` (lint/types/tests matrix 3.11-3.13 + build),
  `upstream-watch.yml` (daily cron, non-graphical subset of the
  pipeline in a container, automatic issue), `release.yml` (tag `v*` →
  checks then GitHub Release, without packaging artifacts since the
  removal of T09). See `docs/CI.md`.

## Phase 4 — Hardening (opened on 2026-08-17)

From a state-of-the-art review conducted on 2026-08-17 on the other tools of
the Linux/GAMMA ecosystem. Of ten leads kept, four were already
covered by us; six become tasks.

- **T11** ✅ Path guards on `uninstall --game-data`. The path is
  resolved then validated once by `paths_safety.validate_wipe_target`
  just before the `rmtree` (system roots, `$HOME` and neighbors, current
  directory, in-progress repo/venv, relative paths, symlinks, depth
  too low, install marker required) — no second `resolve()` that
  would reopen the TOCTOU window. Interactive confirmation (resolved path,
  estimated size) with `--yes` for scripted use.
- **T12** ✅ MD5 integrity of **installed mods** + targeted repair
  (`integrity/`, `verify [--repair]` command + button in the Diagnostic view).
  We only verified archives (`check-md5` from the engine), not the content
  on disk: a mod file corrupted after install was
  undetectable. Reference `gamma-md5.txt`, diff in four categories,
  repair of only the upstream mods damaged, user additions never
  touched — including the mod folder that contains them. See
  docs/ARCHITECTURE.md "Installed mod integrity".
- **T13** ✅ Lock "prefix in use" (commit `9b8e44a`).
  `prefix.session.require_free` is wired to the four destructive operations
  — `install --only prefix` (`orchestrator.py`), `update`,
  `prefix-doctor --repair` and `uninstall --game-data` — with `--force` everywhere.
  Detection by `wineserver` of the prefix, then MO2, then the game.
- **T14** ✅ Launch log diagnostics: `mo2/diagnostics.py` covers
  USVFS **and** failures that occur upstream (`concrt140.dll`,
  `version mismatch` of a prefix built by another Proton). Rewired after
  the fact by T18, which also closes the two remaining false positives (log
  append-only, non-fatal prefix warning).
- **T15** ✅ **tested for real (2026-08-22, full test install, umu 1.4.1
  + GE-Proton11-3)** `play` detached from the terminal: qualified (only the
  direct command-line launch was concerned, neither the `.desktop`
  direct nor the GUI), confirmed by SIGHUP simulation (`forkpty`), fixed
  (`prefix.process.run_detached` — `start_new_session=True` **and**
  `stdin=DEVNULL`, see `docs/MO2-PROTON-COMPAT.md`). The first attempt
  (`start_new_session` alone) still failed for real: the internal sandbox
  of umu-run (`srt-bwrap`) took the inherited stdin as its own control terminal
  and was killed along with the whole chain underneath — `stdin`
  had to be cut too. Replayed with the complete fix: the whole chain
  up to `AnomalyDX11.exe` survives closing the terminal.
- **T16** ✅ **resolved (2026-08-22)** Pinning `WINESERVER` under umu:
  measured on three real launches (GE-Proton11-3, GE-Proton9-20,
  GE-Proton11-1) by reading `/proc/<pid>/environ` and `/proc/<pid>/exe` —
  no client/server decoupling exists on this path, the container
  replacing `/usr` makes the host's wineserver unreachable anyway.
  No patch. Written in `docs/MO2-PROTON-COMPAT.md`.

Already covered, hence set aside in the review: working around the rate limit of
the GitHub API (`updates.py` documents it; `prefix/umu.py` and `prefix/download.py` have
their `FALLBACK_*` fallbacks, distinction compat-data / `pfx`
(`prefix/paths.py`), preservation of unknown keys in `ModOrganizer.ini`
(`mo2/ini.py`), AppImage packaging (out of scope since T09).

## Phase 5 — Adoption (opened on 2026-09-07)

From a comparative review with the **official Windows launcher**. The finding
that guides the whole phase: the official launcher has *three buttons* (*First
Install Initialization*, *Install / Update GAMMA*, *Play*). We already have in
addition resume after interruption, `verify --repair`, `doctor`,
prefix-doctor, `import`, the prefix lock and the anonymized issue report.
**There is no parity to catch up on.** These six tasks therefore aim at two things:
what only Linux allows, and the failure modes that make people quit. Breakdown:
[../tasks/](../tasks/).

- **T17** ✅ **tested for real (2026-09-07, test install, GAMMA 920)**
  Backup/restore + **modlist fusion**. Complaint no. 1 of GAMMA
  on all platforms: the official wiki writes that every "Install / Update
  GAMMA" resets modlist, settings and mod settings. Delivered: package
  `backups/` (profiles, **game saves**, `overwrite/`), commands
  `backup [--list]` / `restore <id> [--dry-run]` + buttons in the Diagnostic
  view, TOML manifest, 5-automatic rotation that always spares
  explicit backups, and `paths_safety` in front of every `rmtree`;
  `orchestrator.backup_mo2_profiles` was **moved** there, not duplicated. The
  part that matters: a **three-way fusion** of `modlist.txt` every
  update (`mo2/modlist_merge.py`), which replays the deactivations, the order and
  the player's additions over the upstream list — and refrains, saying so
  rather than guessing. `update --no-merge` keeps the old behavior.
  Real location of game **observed before coding** (see
  docs/ARCHITECTURE.md "Backup, restore, and modlist fusion".
  Goal reached: we go from "reversible" to "it's no longer lost".
- **T18** ✅ **verified on two real X-Ray logs (2026-09-07)** Session post-mortem
  of session: `postmortem` command + button "Did the game crash?" in the GUI,
  which re-read, once the game is closed, the launch log, the X-Ray engine log
  and the USVFS one to give **one** diagnostics — and name the mods
  to look at first when the trace points to a file
  (`integrity.report.mod_of`, reused, not duplicated). Verified on a real
  crashed game (the suspect mod is correctly named) and on a real game
  quit normally (no false alarm at crash). The result is added to the report
  doctor --report, anonymized like the rest. The finding that oriented all the
  work: on a perfectly healthy session, searching for `[error]` or
  `stack trace` give 65 and 27 false positives — only the patterns **anchored at the start
  of the line** discriminate (see docs/MO2-PROTON-COMPAT.md). Two false positives
  pre-existing fixed along the way: the launch log is append-only
  (only the last session counts) and the non-fatal prefix warning
  measured in T16 no longer masks a real crash.
- **T19** ✅ Steam / Gaming mode in one click: `steam-shortcut` writes the entry
  **and** its artwork in `shortcuts.vdf`, without the user touching
  Steam. **Reverses the T06 out-of-scope** : the "gain limited to players
  Deck" has become the growing audience, and in Gaming mode the user *can't*
  follow our instruction ("Add a non-Steam game" requires the Desktop
  mode). The T06 reservations have become the spec: VDF codec
  written against a real file and validated in **byte-to-byte round-trip**
  (anonymized real fixture in `tests/`), timestamped `.bak` backup +
  atomic write, refusal to write while Steam is running, preservation
  field by field of the other shortcuts, `--remove` that returns the file as
  before. Verified end to end on the real Steam install of the machine on
  2026-09-08 (add, no duplication, removal byte for byte).
- **T20** ✅ **delivered and verified in-game (2026-09-08)** — two of three layers
  kept. MangoHud and vkBasalt are composed around the launch by
  `environment/performance.py`: `gamemoderun` in contact with `umu-run`, the two
  Vulkan layers by environment variables (their manifest declares
  `enable_environment`, so no wrapper scripts). Both are **off by
  default** and appear in `doctor` as optional, with the command
  for their distribution (vkBasalt: AUR on Arch, there's no package
  official). vkBasalt is delivered with **our** "ReShade-like" preset (CAS +
  generated LUT): the README promise is finally kept on the code side. The hard part —
  the visibility of the Vulkan layers **inside** the pressure-vessel container — had
  been worked out by reading the sources for lack of GPU in the batch environment
  of the lot; it was **raised on the dev machine**, then **confirmed in-game**:
  `libMangoHud.so` and `libvkbasalt.so` are both loaded in
  AnomalyDX11.exe (ELF 64-bit) from `/run/host/usr/lib64/`, and vkBasalt
  logs having read our preset without an error. The `VK_ADD_LAYER_PATH` fallback
  is **not** needed. **A bug found and fixed along the way**: `doctor`
  showed `[ OK ] vkBasalt` on the faith of the manifest alone, whereas with the
  sole 32-bit library the layer doesn't load in a 64-bit game, in
  total silence — `vulkan.layer_abi_support()` now reads the ELF class.
  ⚠ **gamescope/FSR was removed** the same day: nested under KWin, it dies
  on a Wayland protocol error (`xdg_surface` error 3) and its *reaper*
  takes the game with it. It was neither our composition nor our options (replayed
  identically, they work) but a class of bug known upstream, which
  doesn't apply on Steam Deck — where gamescope *is* the session. Without a Deck
  to check the nominal case, we don't deliver a switch that kills the
  game on the only testable machine. Conditions for a return: docs/ARCHITECTURE.md.
  ⚠ **Known debt** : the vkBasalt upstream is dead (last commit Oct. 2023,
  80 open issues). We keep it because it's the only packaged one and it
  works; the successor to watch is vkShade, to switch when it
  leaves pre-alpha **and** enters the repositories.
- **T21** ✅ **delivered (2026-09-14)** — Shader cache outside the prefix.
  `DXVK_SHADER_CACHE_PATH`, `MESA_SHADER_CACHE_DIR` and
  `__GL_SHADER_DISK_CACHE_PATH` (plus the size caps, and the variable
  driver set only if the corresponding driver is detected) are set
  by default under `<root>/cache/shaders/` by `environment/shader_cache.py` —
  spared by `install --only prefix`, `prefix-doctor --repair` and a
  Proton-GE version change, where `install --only prefix` (our
  official remedy for "prefix has an invalid version") used to
  silently lose hours of compilation. Measured for real (cold
  to warm cache, zero bytes recompiled for the same rendered content); the
  automatic preheating is not implemented, for lack of an automation tool
  for entry under Wayland to go beyond the menu. `prefix-doctor
  --purge-shaders` forces a full recompilation or reclaims the space
  of orphan entries (same guard as `--repair`: refuses if the prefix is
  busy, `--force` overrides); never touches the X-Ray cache. Detail
  in docs/MO2-PROTON-COMPAT.md.
- **T22** ✅ **delivered (2026-09-14)** — ModDB resilience. Upstream issue opened
  (#282, Cloudflare captchas), plus #286/#284/#283. The recognition of
  markers of `verify()` is extended to the download path
  (anomaly-install/full-install) via a single table (`engine/markers.py`)
  that classifies a ModDB failure into three distinct causes — network/ModDB
  unreachable, broken mod link (manual repository), corrupted local archive
  (automatic removal) — instead of a raw traceback. The named failures
  are remembered in the persisted state for an honest report at the end
  of the installation, and `install --retry-failed` replays only these mods
  reusing the mechanism of `integrity/repair.py` (T12) already used by
  `verify --repair`; a file placed by hand (`<gamma>/downloads`) is
  verified by MD5 before restarting the engine, when that MD5 is known.
  Explicit scope respected: **no protection bypass**.

- **Interface overhaul** ✅ **delivered (2026-09-07)**: the GUI skinning
  takes up the grammar of a game launcher: the Zone artwork redone in
  layers (Duga antenna, reactor chimney, pylons, ground mist,
  anomaly) and calibrated, title bar carrying the system status, low "bridge"
  structured (identity, figures, actions), status tiles — free space,
  deployed mods, version —, disk space gauge at the install dialog,
  progress timeline staked out on a rail. Foundations side: the style sheet
  becomes a real CSS file (`gui/theme/style.css`, palette in
  `@define-color`, validated by a test), the artwork is no longer decoded more than
  once for the whole application, the seven branches of long tasks come out
  of `main_window.py` (`gui/jobs.py`, testable without a window), and
  `scripts/capture_screenshots.py` regenerates the documentation off-screen, on an
  demonstration install. Two bugs fixed along the way: the console of
  progress could show up empty even though its buffer was full (view
  scrolled under its content when the log fit in the window), and the
  style sheet produced a GTK warning by redrawing by redefining
  the geometry of the Adwaita scrollbars.

**The main brake is not functional.** Same review: 5 stars, 0
issue, 0 fork. Three levers, outside the task sheets above — an **AUR** package
then **COPR** (the reasons for T09's removal, sandbox vs Wine/Proton, don't
apply to a native package); a presence in the **Linux guides of the
GAMMA wiki** and its Discord; **i18n beyond en/fr** (ru/uk/pl/de).

## Out of scope (assumed)
- Native portage of the Monolith X-Ray engine (without Proton): a project of
  another scale, Proton is the answer for years to come.
- Rehosting of mods or the game.

## Tracked risks
- MO2/USVFS fragility by Proton versions → compatibility matrix delivered
  (`docs/MO2-PROTON-COMPAT.md`) + auto diagnostics + flat fallback (T05).
- Rate-limit / ModDB mirror changes → handled upstream (gamma-launcher).
- GAMMA update cadence → non-regression CI (T10).
