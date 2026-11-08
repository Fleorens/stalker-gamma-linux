# MO2 × Proton × USVFS compatibility matrix (state of the art 2025-2026)

> **Role of this document**: arbitrate the choice of Proton version for the
> **main mode** of `stalker-gamma-linux` — Mod Organizer 2 running under
> Proton with **USVFS active**, the only way to preserve mod flexibility
> (enable/disable/add) required by the project.
>
> It is referenced by the code: the post-launch diagnostic
> (`mo2/diagnostics.py`) sends the user here when it detects a dead USVFS
> dead (game launched "vanilla"). Written on 2026-07-22 from cross-referenced
> sources listed at the end of this document.

## TL;DR — recommendation

1. **Project default: the latest GE-Proton release** (user decision
   2026-07-19, handled by `prefix/`). On Wine 9/10, USVFS works in the
   vast majority of cases — **validated in the field on 2026-07-22** with
   **GE-Proton11-1** on a complete GAMMA install (MO2 open, 577 mods
   served via USVFS, Anomaly DX11 launched and played).
2. **If the game starts in "vanilla" (0 mod, dead USVFS)** — symptom No. 1 of
   this document — switch to **Proton 9.0 or 10.0 *vanilla* from Steam**: it's
   the most reliable and most reported combination for USVFS + MO2. The
   `prefix/` already accepts "Proton - Experimental"; for a precise GE/vanilla,
   put it in `compatibilitytools.d` and relaunch.
3. **Never** stay under **Proton ≤ 8.x / GE-Proton8-x** with the MO2 2.5.x
   shipped by GAMMA: these builds are **under Wine 8.0**, predating the required
   USVFS fix (see "Why it breaks"). It's the most common trap.

The **flat** mode (`gamma-launcher usvfs-workaround`, annex A of
`INSTALL-MANUAL.md`) remains the last resort if no Proton version
   mounts USVFS on the machine — at the cost of mod flexibility.

## Why it breaks (technical root cause)

MO2 does not copy mods into the game: it mounts a **local virtual file
system local to the process** (USVFS, `usvfs_x64.dll`) by *API hooking* of
Windows file calls. Only processes launched **from MO2** see this
overlay — hence the obligation to launch the game *through* MO2 (`moshortcut://`),
and not the executable directly.

Under Wine/Proton, this hooking requires recent Windows syscalls that Wine
implemented only late:

- **Wine bug 46697**: USVFS (MO2 ≥ 2.1.1) requires
  `ntdll.NtQueryDirectoryFileEx` (Windows 10 build 1709+ syscall). The two
  required fixes first landed around **Wine 4.21**.
- **MO2 2.5.x** (the lineage shipped by GAMMA) goes further and requires a
  additional fix **available only from Wine 8.21**: in Nov. 2023,
  *no* Proton/GE build carried it yet, and SteamTinkerLaunch pinned
  MO2 **2.4.4** meanwhile. This fix is today present throughout the
  lineage **Wine 9.x / 10.x**, hence in **Proton 9.0, 10.0** and the GE-Proton
  equivalents.
- **Observed in the field (GE-Proton11-1, Wine 10, usvfs 0.5.6.1)**: usvfs fails to
  hook `NtQueryDirectoryFileEx` (`failed to hook NtQueryDirectoryFileEx: No
  Error`) but **hooks the old `NtQueryDirectoryFile`** and the VFS works
  perfectly. The "Ex" fix of Wine 8.21 is therefore not strictly
  required on this stack; the fallback hook is enough for GAMMA.
- **GE-specific regressions**: historically, USVFS worked under the
  Proton *vanilla* from Valve while **failing on certain GE builds** (additional
  GE patches that regressed the hooking), *even while* the
  Wine fix was present. This is exactly the "the game launches but in
  vanilla" scenario: Wine recent enough, but VFS not mounted. Hence the rule: GE by
  default, **fallback to Proton vanilla 9/10 if the diagnostic fails**.

Known overhead: Windows→Wine hooking adds a noticeable CPU cost (context-switching)
on large modpacks like GAMMA. Experimental native lead:
**RadTux** (replaces USVFS hooks with a Linux VFS daemon) — out of scope,
`⚠ NEEDS VERIFICATION` for GAMMA.

## Matrix

Status: ✅ works · ⚠️ variable/watch · ❌ broken. "MO2 GAMMA"
   designates the lineage **2.5.x** packed in the instance shipped by
   gamma-launcher.

| MO2 | Proton / GE | Base Wine | USVFS | Notes & source |
|---|---|---|---|---|
| 2.5.x (GAMMA) | **Proton 10.0** (vanilla Steam) | 10.x | ✅ | Recommended 2025 by GAMMA guides (v1ld). Most reliable with 9.0. |
| 2.5.x (GAMMA) | **Proton 9.0** (vanilla Steam) | 9.x | ✅ | "Proton 9.0 recommended" (modorganizer2-linux-installer). Safe bet. |
| 2.5.x (GAMMA) | **Proton - Experimental** | 10.x+ | ⚠️ | Contains the latest fixes, but changes every week: may break then self-heal. Accepted by `prefix/` when no GE is available. |
| 2.5.x (GAMMA) | **GE-Proton11-1** | 10.x | ✅ | **Validated in the field (2026-07-22)**: USVFS 0.5.6.1 mounted, 577 mods served, a playthrough played. This is the project default. |
| 2.5.x (GAMMA) | **GE-Proton10-x (latest)** | 10.x | ⚠️→✅ | OK on recent builds; in case of "vanilla", fallback vanilla 9/10. |
| 2.5.x (GAMMA) | **GE-Proton9-20** | 9.x | ✅ | GE version explicitly cited as working (wiki FaithBeam). Good pinned GE fallback. |
| 2.5.x (GAMMA) | **GE-Proton8-x** | 8.0 | ❌ | Before Wine 8.21 → MO2 2.5 fix absent. To avoid. |
| 2.5.x (GAMMA) | **Proton ≤ 8.0** (vanilla) | ≤ 8.0 | ❌ | Same: MO2 2.5.x does not mount USVFS. A classic trap. |
| 2.4.4 | Proton 7/8 | 7–8 | ✅ | Historical SteamTinkerLaunch fallback combination. Out of scope (GAMMA ships 2.5.x). |
| all | Proton 5.0–9 (vanilla) | ≥ 4.21 | ✅ (Bethesda games) | USVFS OK under Proton vanilla "but not the GE builds" back then (rockerbacon). Illustrates the GE regression. |

> The ⚠️ cells do not mean "do not use": they mean
> "let the post-launch diagnostic decide and prepare the fallback". The most recent GE
> is the default *precisely* because it brings the other
> game fixes; we only give it up if USVFS does not mount.

## Symptom → remedy (used by diagnostics)

| Observed symptom | Likely cause | Remedy (in order) |
|---|---|---|
| The game starts but **without GAMMA content** (vanilla menu/HUD); the instance USVFS log does not show `proxy run successful` | **Dead USVFS**: incompatible Proton version, or game launched outside MO2 | 1) Check that you launch via `moshortcut://` (`play` mode, not the direct exe). 2) Switch to **Proton 9.0/10.0 vanilla**. 3) Try **GE-Proton9-20**. 4) Last resort: **flat mode** (`play --flat`). |
| MO2 opens but **0 active mods** | Wrong game folder / profile, instance not configured | Reconfigure the instance (`gamePath` → Anomaly folder, profile `G.A.M.M.A`) — automated by `mo2/instance.py`. |
| MO2 **does not start at all**, launch log mentioning `concrt140.dll`, `msvcp140.dll` or `vcruntime140.dll` | Missing VC++ 2015-2022 runtimes in the prefix (verbs not set, or a cobbled/partially repaired prefix) | `stalker-gamma-linux prefix-doctor --repair` (replaces the missing verbs). |
| Unreadable Wine error at launch: `wine client error:0: version mismatch`, `wrong wineserver`, `prefix has an invalid version`, `your wine binary was not upgraded correctly` | The shared prefix was built by a **different Proton version** than the configured one. This is **not** a `wineserver` selection problem (measured, cf. "`WINESERVER` under umu"): it's the prefix version control by Proton | `stalker-gamma-linux install --only prefix` (rebuilds the prefix from scratch with the currently configured Proton). |
| Poor perf (heavy shader mods) | USVFS overhead + heavy shaders | Disable Screen Space Shaders / Shaders Cumulative Pack; evaluate RadTux (`⚠ NEEDS VERIFICATION`). |

Detection (`mo2/diagnostics.py`): `diagnose_launch_log` reads the umu-run
launch log (`prefix.process`, `logs/mo2-game.log` of the install — see
"Detached launch from terminal" below for this fixed name) looking for
the two failures **upstream** of USVFS above (missing VC++ runtime,
prefix from another Proton version) — case-insensitive search. If
either is recognized, its remedy message must be shown **instead**
of the USVFS diagnostic (a user told about two problems fixes neither):
these failures prevent the target process from starting, so
USVFS never had the slightest chance of mounting.

> Since T15 (`play` detached, see below), `run_play` **no longer calls these
> functions automatically**: the game is still running when `play` returns
> control, so reading them then would be a systematic false negative
> (nothing has had time to be written yet). `diagnose_launch_log`/
> `diagnose_usvfs` remain usable **afterwards**, once the game is closed
> (T14 of `docs/ROADMAP.md`, not yet wired into a dedicated command) — that's
> why `play` now announces the log path instead of diagnosing
> itself.

Otherwise, we read the latest `logs/usvfs-*.log` of the instance and look for
the markers of a **live VFS** found on a real run that works (usvfs
0.5.6.1, GE-Proton11-1): `inithooks in process <pid> successful` (hooks set
in the game process) and `mapping file in vfs:` (the VFS actually serves
files). Absent ⇒ warning (not a failure: `play` succeeds if the game
launched). We also check that the profile `G.A.M.M.A` has active mods
(`modlist.txt`, lines `+`).

> The marker `proxy run successful` cited by forum guides **does not
> exist** in usvfs 0.5.6.1: using it gave a false negative (observed
> in the field on 2026-07-22).

## Detached launch from terminal (T15, 2026-08-22)

**Qualification.** Three launch paths for the game, examined separately:

1. `.desktop` entry "Play GAMMA (direct)" (`desktop/entry.py`): `Terminal=false`,
  no controlling terminal to close — **not concerned**, by construction.
2. GUI (`gui/worker.py`): the operation runs in a daemon thread **of the same
  process** as the GTK window; closing the window signals nothing to the
  child process (umu-run/Wine), which is in any case launched without
  a controlling terminal when the GUI starts from its `.desktop` — **not concerned**.
3. `stalker-gamma-linux play` on the command line: **this was the
  problematic case**. `prefix.process.run_in_prefix` launched `Popen` without
  `start_new_session`: the child inherited the session/process group of
  the calling terminal. Reproduced with a pseudo-terminal
  (`os.forkpty` + closing the master side, which sends SIGHUP to the process
  group at the foreground of the session — same mechanism as a terminal
  you close): the child process **died** within the second.

**Correctif.** `prefix.process.run_detached()` (new sibling function of
`run_in_prefix`, dedicated to game launches): `start_new_session=True`,
`stdin=DEVNULL`, output redirected straight into a single log file per
launch (`logs/mo2-game.log` / `logs/flat-game.log`, no more per-launch
timestamp), rotated (1 backup `.log.1`) beyond 5 MiB, descriptor
closed on the parent side as soon as `Popen` returns. `mo2.launch.launch_game` and
`mo2.flat.launch_flat` now use it; `mo2.launch.launch_mo2`
(MO2-only interface, `mo2` command) and the whole installation pipeline
(`engine`/`prefix.provision`) stay on `run_in_prefix`, blocking with
progression/`cancel_event` — two explicit modes, never a mode that guesses
which one it is.

**Revalidated in real conditions** (2026-08-22, complete test install
`/mnt/games_lexar/Games/GAMMA-test`, umu 1.4.1, GE-Proton11-3), same method
of the qualification (`os.forkpty` + closing the master side = same
SIGHUP mechanism as a real terminal you close), but against the real `play`
launching the real MO2/Anomaly:

- **First attempt, with `start_new_session=True` alone (no `stdin=DEVNULL`)**:
  failure. `play` returns control immediately (detached mode OK), but
  closing the terminal just after killed **all** the umu-run sandbox
  (`srt-bwrap`, Proton, wineserver, MO2, the game) a few seconds after its
  launch. Cause identified by process inspection (`ps -eo
  pid,ppid,sid,pgid,tty,stat`): `run_detached` still inherited the
  `stdin` of the calling terminal (nothing redirected it); the internal
  umu-run sandbox (`srt-bwrap`, steam-runtime/pressure-vessel) itself does a
  `setsid()` then takes that descriptor back as **its own** terminal of
  control via `TIOCSCTTY` — possible because the original session becomes
  orphaned as soon as `play` returns control (no living process left in it).
  `bwrap` ended up being the foreground process of the pseudo-terminal:
  closing it sent SIGHUP, which killed all the sandbox below —
  the symptom we thought we had fixed, reproduced one level down, inside
  umu-run itself.
- **With the complete fix (`stdin=subprocess.DEVNULL` added)**: success.
  Same scenario replayed exactly (same install, `play` relaunched): after
  the simulated closing of the terminal, the whole chain (`umu-run` → `srt-bwrap` →
  `pv-adverb` → `proton` → `wineserver` → `explorer.exe`/`ModOrganizer.exe`
  (`main`) → **`AnomalyDX11.exe`**, the game engine) stayed alive and
  kept progressing (the game finished starting *after* the simulated
  closing). No process in the chain has a controlling terminal anymore
  (`tty=?` everywhere in `ps`).

Consequence for `play`: the command no longer blocks until the game is
closed, it announces the log path and returns control immediately. The
automatic USVFS diagnostics after launch (`--no-diagnose`) was removed
at the same time — it no longer made sense in detached mode (see above).

## `WINESERVER` under umu — settled question (T16, 2026-08-22)

**Question asked.** When MO2 launches the game through USVFS, a system `wineserver`
(`/usr/bin/wineserver`, present on this machine: `wine-core-11.0-3.fc44`)
or that of an older Proton — can one be selected instead of the one from the
Proton of the prefix? A client and a mismatched Wine server produce exactly
the `version mismatch` that launch diagnostics learn to recognize. The
known workaround on a direct `proton run` from Steam is to force
`WINESERVER=<proton>/files/bin/wineserver` — but that's not our path: we
go through `umu-run`, which manages its own runtime.

**Answer: no. No decoupling exists on this path, and `WINESERVER` does not have
to be forced.** `_prefix_environment` stays unchanged — this is the settled
question that has value, not a patch. The detail below documents *why* it's
structural and not a matter of luck, so that we don't have to ask the question again.

### Measurement method (reproducible)

The decisive point is to **not rely on environment variables alone**:
they say what was *asked*, not which binary *won*. For each
process in the chain whose `/proc/<pid>/environ` points at the shared prefix, we
record both:

- `WINESERVER`, `WINELOADER`, `PROTONPATH` (in `/proc/<pid>/environ`);
- **`readlink /proc/<pid>/exe`** — the binary actually executed, the only verdict.

Three real launches on the test install (`/mnt/games_lexar/Games/GAMMA-test`,
umu 1.4.1), each up to a living `AnomalyDX11.exe`, forcing `PROTONPATH` via
the project code (`mo2.launch.launch_game`) — hence the real path MO2 →
`moshortcut://` → USVFS → game, not a synthetic bench. The prefix was
backed up before and restored after (the launches rewrite it, see below).

### Readings

Prefix built by **GE-Proton11-3**. `AnomalyDX11.exe` reached in all three cases.

| Launch | Forced Proton | Wine base | `WINESERVER` | Actual `wineserver` executed | Loader for MO2 **and** the game | `/usr/bin/wineserver` used |
|---|---|---|---|---|---|---|
| 1 | GE-Proton11-3 (= the prefix's) | 11.0 | ∅ not set | `GE-Proton11-3/files/bin/wineserver` | GE-Proton11-3 | no |
| 2 | **GE-Proton9-20** (older than the prefix) | 9.0 | ∅ not set | `GE-Proton9-20/files/bin/wineserver` | GE-Proton9-20 | no |
| 3 | GE-Proton11-1 (after the 9-20) | 11.0 | ∅ not set | `GE-Proton11-1/files/bin/wineserver` | GE-Proton11-1 | no |

In all three cases, **a single Proton dist across the whole chain** (13, 11 and 14
processes respectively: `wineserver`, `services.exe`, `explorer.exe`,
`ModOrganizer.exe`, `AnomalyDX11.exe`…), and `WINESERVER` set **nowhere** —
including on the game's child process, where the decoupling was supposed to
happen. No `version mismatch` nor `wrong wineserver` on any of the three.

`WINELOADER`: not set under GE-Proton11-x (wow64 build), set by Wine itself
under GE-Proton9-20 (`.../GE-Proton9-20/files/bin/wine64`) — consistent with the same
dist in both cases.

### Why it's structural

Four layers, none of which leaves room for decoupling:

1. **umu never sets `WINESERVER`**: zero occurrence of the string in
   the entire umu-launcher zipapp 1.4.1 (177 entries). The starting hypothesis
   ("umu probably already sets a coherent `WINESERVER`") is therefore false
   in its letter — but the conclusion stands for another reason, the next one.
2. **Proton doesn't set it either**: zero occurrence of `WINESERVER` in its
   script `proton`. It keeps its `wineserver_bin` as an internal path
   (`files/bin/wineserver` relative to its own dist) and just prefixes
   its `bin_dir` to the `PATH`.
3. **Wine derives it itself.** `WINESERVER` not set, `ntdll.so` resolves the
   server **relative to the loader that loaded it** (`server/wineserver` +
   `getenv("WINESERVER")` as an optional override, visible in the symbols of
   `files/lib/wine/x86_64-unix/ntdll.so`). The `cmdline` of the measured `wineserver`
   shows it literally:
   `…/GE-Proton11-3/files/lib/wine/../../bin/wineserver` — a path derived from the
   `ntdll.so` loaded, neither a `PATH` nor a variable. Client and server come from
   the same dist **by construction**.
4. **The container makes the host wine unreachable.** In the umu sandbox
   (pressure-vessel, Steam Runtime 3/4), the host's `/usr` is *replaced*:
   `/usr/bin/wineserver` doesn't exist, `wineserver` is not on the `PATH`
   (`/usr/bin:/bin`). The Fedora wine is only visible in `/run/host/usr/bin/wineserver`,
   a path no Wine loader checks. The scenario "the system wineserver is
   selected" is therefore **impossible** under umu, not just unlikely.

### Why you should not set `WINESERVER` "just to be safe"

At best it would be redundant, at worst harmful: umu **rewrites** `PROTONPATH` in
several cases (code name like `GE-Proton`, fallback `UMU-Latest`, container runtime
resolution — `umu_run.py`, resolution of `PROTONPATH` before launch). A
`WINESERVER` derived from the `PROTONPATH` that *we* pass would then point to a
different dist than the one umu ends up mounting — which would **create** the
decoupling the variable was supposed to prevent. The current selection is correct
because it's derived at the end of the chain, by the loader actually loaded.

### Measured side effect: `Prefix has an invalid version?!` is not fatal

Launches 2 and 3 ran a Proton on a prefix built by another one. Proton detected it,
announced it, then **kept going**:

```
Proton: Upgrading prefix from GE-Proton11-3 to GE-Proton9-20 (…/prefix/)
Proton: Prefix has an invalid version?! You may want to back up user files and delete this prefix.
```

…and the game still launched, USVFS included, rewriting the `version` of the
prefix along the way (hence the backup/restore in the method). Two
consequences:

- The `version mismatch` that launch diagnostics recognize belongs to the
  **version of the prefix**, not the `wineserver` selection: forcing
  `WINESERVER` would change nothing there. The remedy from the table above
  (`install --only prefix`) is still the right one — a prefix rewritten from one Wine base to
  the other keeps its verbs and its overrides set for the other.
- `prefix has an invalid version` is part of the markers of
  `mo2/diagnostics.py` (`_PREFIX_VERSION_MARKERS`), yet it appears here on
  successful launches: read afterwards, the diagnostic would conclude a prefix failure
  even though the session started. Known false positive, to be handled on the T14 side —
  out of scope for this task, which does not touch the code.
  **Handled in T18** (see "Post-mortem of session" below): the
  post-mortem does not pit one message against another, it compares the dates of
  modification of the two logs. If the engine ran during *this* launch,
  the prefix warning is not this session's story and the crash
  takes back first place. The markers themselves are unchanged: they
  stay correct when the process does not start.

## Post-mortem of session — X-Ray engine log (T18, 2026-09-07)

What the "Symptom → remedy" table above did not cover: **the game
started, with its mods, and crashed mid-session.** The log
umu-run says nothing about this case; the only place to read it is the
engine itself, which nothing had opened until now.

### Log location — observed, not assumed

On **both** real GAMMA installs on the development machine, the
engine writes in the *Anomaly* folder, not in the MO2 instance:

```
<anomaly>/appdata/logs/xray_steamuser.log
```

`steamuser` is the Windows account of the Proton prefix (hence the search by
glob `xray_*.log`). The USVFS write redirection — everything a
process launched from MO2 creates lands in `overwrite/` — **did not happen**
: `appdata/` is outside the virtualized tree (verified:
`gamma/overwrite/` contains only `AnomalyLauncher.cfg`, `commandline.txt` and
a `gamedata/`). It remains possible depending on the instance configuration, so
`postmortem/logfile.py` searches at **both** locations and keeps the file
most recently modified — the name not being timestamped, unlike the
`usvfs-*.log`, it's the date that settles it.

The log is rewritten at every launch (a single `Game started:` per
file) and commonly runs to several megabytes: 5.2 MiB / 104,329 lines on
the measured session. It is therefore never loaded in full — header on one side,
tail on the other.

### The trap: `[error]` and `stack trace` are not crash markers

Measured on a session **quit normally** (13/08/2026, 104,329 lines):

| Pattern searched | Occurrences on the **clean** session | on the **crashed** session |
|---|---|---|
| `[error]` (case-insensitive, anywhere) | **65** | 55 |
| `stack trace` (same) | **27** | 63 |
| `^stack trace:` (anchored at line start) | **0** | **1** |
| `^FATAL ERROR` | 0 | 0 |
| `^[xrLogger] InternalCloseLog` | **1** | **0** |

The 65 and the 27 are GAMMA *application* errors, from which the engine recovers
itself: `! [ERROR] --- Failed to load script mags_patches`,
`~ STACK TRACEBACK:`. The player played another hour behind. What
distinguishes the engine's fatal block is that it starts **at line start** —
Anomaly always prefixes its own with a `! ` or a `~ `. The patterns of
`postmortem/markers.py` are therefore anchored; case-insensitivity becomes
harmless then.

### Markers kept, and where they come from

- **Clean end**: `[xrLogger] InternalCloseLog called, terminating thread` —
  last line of the clean session, preceded by the `RM_Dump` from the resource
  manager.
- **Crash**: `stack trace:` at line start, followed by the dump
  `SymInit: Symbol-SearchPath:` / `OS-Version:` / `at address 0x…`, and no
  `InternalCloseLog` behind. This is exactly what the session
  crashed on 26/08/2026 ends on (`at address 0x0000000140B02DC1`).
- **Fatal block**: `FATAL ERROR` alone on its line, then
  `[error]Expression    : …`, `[error]Description   : …`. Neither of the two
  sessions contains any; the formats come from the strings of the binary itself
  (`%sFATAL ERROR%s%s`, `%sExpression    : %s%s` in
  `anomaly/bin/AnomalyDX11.exe`, cf. `xrDebugNew.cpp`).
- **Out of memory**: `Out of memory. Memory request: <n> K` and
  `* [x-ray]: OOM requesting <n> bytes`. **Never observed case**: formats taken
  from the binary (`out_of_memory_handler`), and it's written as-is in the code
  rather than letting one believe we saw it run.

When no end marker appears, the verdict is "I can't
conclude": the session may still be running.

### Mod attribution — a suspect, not a culprit

The engine never names a mod, it names a file. On the crashed session,
the last lines before the trace are:

```
! error in stalker [sim_default_csky_2], profile [dick_sim_default_csky_2_default_34]
  with visual [actors\stalker_nebo\stalker_nebo3_exohead]
stack trace:
```

`gamedata/meshes/actors/stalker_nebo/stalker_nebo3_exohead.ogf` exists: it is
provided by `29- Dux's Innemurable Characters Kit - DuxFortis`. But
`31- Fixed Vanilla Models and Textures - Blackgrowl` provides the rest of the
`stalker_nebo/` folder **without** this file. The named mod is therefore the one to look at
first, not the one to accuse: the culprit may be its neighbor in the
load order. Hence the wording "suspect", and the list of *all* the
owners found.

The path → mod mapping is not rewritten: it's `integrity.report.mod_of`
that decides, as for `verify`.

### Launch log: append-only, hence last session only

`prefix.process.run_detached` opens `logs/mo2-game.log` in **append** — the
file of the measured install contains three launches. Diagnosing the file
in full would surface a failure from three weeks ago as if it had just
happened; `mo2.diagnostics.last_launch_session` therefore keeps only the last
`$ <command>` block. In passing, reading this log has become tolerant
of non-UTF-8 bytes: `run_detached` redirects the raw process output here,
without the `errors="replace"` that `run_in_prefix` applies to its stream, and a single
invalid byte (0x88, observed on the Wine side) would silence the diagnostic without a word.

## DXVK/Mesa/NVIDIA shader cache — measurement and decision (T21, 2026-09-09/14)

**What changed.** `DXVK_SHADER_CACHE_PATH`, `MESA_SHADER_CACHE_DIR` (+ its
ceiling) and `__GL_SHADER_DISK_CACHE_PATH` (+ its own) are now set by
default in `prefix.process._prefix_environment`
(`environment.shader_cache.build_env`), pointing under
`<root>/cache/shaders/{dxvk,mesa,nvidia}` — outside the prefix, so spared by
a reconstruction (`install --only prefix`, `prefix-doctor --repair`). A
driver variable is set only if the corresponding driver is detected present
on the machine (`shader_cache.nvidia_present` / `mesa_present`). See the module
for the details and sources of the variable names — `DXVK_STATE_CACHE_PATH`,
which you can still find in old guides, no longer exists in current DXVK.

**Question raised by T21.** The gain of a persistent cache is obvious in theory
(no recompilation after an `install --only prefix`); the gain of a
**automatic pre-heating** (launching the game once during installation
to populate the cache before the player touches it) is not — still
it must compile something other than what a normal launch would in any
case compile in a few seconds.

### Measurement method, and its limit

Two real launches via `stalker-gamma-linux play` on the install of
`/mnt/games_samsung/Games/GAMMA` (GE-Proton11-3, AMD/Mesa GPU — `radv`, no
NVIDIA driver on this machine), separated by five days:

- **Launch 1** (2026-09-09, cold cache — `cache/shaders/` did not exist
  before): `ModOrganizer.exe` launched, game reached up to the main menu,
  left idle for a few minutes, closed normally.
- **Launch 2** (2026-09-14, warm cache — nothing in between): same
  protocol, same interactive session (main menu, ~1 minute of inactivity,
  normal closure), to compare at equivalent state.

**Assumed limit, not to lose sight of when rereading these numbers later**:
due to the lack of an input automation tool under Wayland available on this
machine (`xdotool`/`ydotool`/`wtype` absent, KDE Plasma 6.7), neither of the
launches went beyond the main menu — no game load, no
movement in game. It's precisely there that the majority of the
shader diversity of a modpack this size (zones, weather, NPCs, weapons…).
The measurement below therefore speaks of the shader cache of the **menu**, not of that
of a real game session.

### Readings

| | Launch 1 (cold cache) | Launch 2 (warm cache) |
|---|---|---|
| `cache/shaders/dxvk/*.dxvk.bin` | 0 → **443,777 bytes** (created) | **443,777 bytes** (unchanged) |
| `cache/shaders/dxvk/*.dxvk.lut` | 0 → 12,445 bytes (created) | rewritten, size nearly identical (12,427) |
| `cache/shaders/mesa/` (radv) | **5.7 MiB** (created) | 5.7 MiB (unchanged) |
| Engine log (`xray_steamuser.log`) | clean shutdown, `DLTX Cache: Files Cached: 2842` | clean shutdown, same numbers |
| Total session duration (launch → closure) | ≈ 3 min 30 (including a wait window not timed precisely) | ≈ 4 min (including ~1 min of deliberate waiting) |

The number that settles it: **zero bytes added** to the DXVK cache state nor to the
Mesa cache at launch 2. For exactly the same rendered content (the menu), the
driver and DXVK had nothing to recompile — the persistent cache does what
is asked of it, in a verified way and not just deduced from the code.

### Decision: no automatic pre-heating

**The persistent cache mechanism (points 1 to 4 of T21) is confirmed by the
measurement above; automatic pre-heating, for its part, is not implemented.**

The reasoning, not just the measurement: an automated pre-heating inserted
into the installation pipeline could not, with the means of this project
(no in-game navigation script, no known benchmark command on the
gamma-launcher/Anomaly side), but launch the game up to the menu — exactly what we
just measured. Yet this subset of shaders already compiles below the
minute on a cold cache (launch 1, above): adding it
to the installation would make the player wait for a gain they would not
notice, without touching the real problem — in-game compilation, which happens
in any case on the first real launch, only once, persistent cache or
not. A pre-heating that does not cover what costs money would be decorative:
precisely what this project avoids (cf. `WINESERVER`, T16, above). A lead
closed cleanly; reopenable if gamma-launcher one day exposes a mode
"traverse all the zones" or equivalent.

### What we will never do: distribute a pre-compiled state cache

A DXVK/Mesa "community" cache, downloaded and placed in
`cache/shaders/` at installation, is explicitly excluded — not for lack
of ideas, but because it violates two rules at once:

1. **It would not work correctly.** The DXVK state cache encodes
   pipelines for a specific GPU and driver version; a cache built
   on a different machine may fail to load, or worse, load a
   pipeline that no longer matches the local driver binary — DXVK validates
   by hash, so the likely case is a silent rejection (no gain), not
   corruption, but it never brings anything to someone who didn't produce it.
2. **That would be rehosting.** Hosting someone else's binary —
   whether it's a shader cache rather than a mod archive — remains contrary
   to the project's rules ("no rehosting ever", already applied to the X-Ray cache
   and to ModDB archives). The fact that this binary is useless outside its
   machine of origin (point 1) doubles the reason not to do it, it does not
   replace it.

## Sources

- MO2 — Linux/Wine USVFS compatibility thread (issue #372):
  https://github.com/ModOrganizer2/modorganizer/issues/372
- usvfs (hooking library):
  https://github.com/ModOrganizer2/usvfs
- Wine bug 46697 (USVFS ↔ `NtQueryDirectoryFileEx`, Win10 1709+):
  https://bugs.winehq.org/show_bug.cgi?id=46697
- ValveSoftware/wine #67 — "Merge USVFS patch":
  https://github.com/ValveSoftware/wine/issues/67
- SteamTinkerLaunch — MO2 wiki (MO2 2.5.0 requires Wine ≥ 8.21, fallback 2.4.4):
  https://github.com/sonic2kk/steamtinkerlaunch/wiki/Mod-Organizer-2
- modorganizer2-linux-installer (rockerbacon/Furglitch) — Proton 9.0
  recommended; "USVFS OK under Proton vanilla but not the GE builds":
  https://github.com/rockerbacon/modorganizer2-linux-installer ·
  https://github.com/Furglitch/modorganizer2-linux-installer/wiki/Post%E2%80%90Install-Instructions ·
  https://github.com/rockerbacon/lutris-skyrimse-installers/issues/156
- GAMMA Linux guide (v1ld, ref. Sept. 2025 — Proton 9/10, MO2 config):
  https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
- FaithBeam wiki (GE-Proton9-20):
  https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Steam Deck guide (maxastyler):
  https://github.com/maxastyler/S.T.A.L.K.E.R.-Gamma-Steam-Deck-Install-Guide/
- Real markers of a live VFS (`inithooks in process N successful`,
  `mapping file in vfs:`): recorded in a `logs/usvfs-*.log` of a working
  GAMMA install (usvfs 0.5.6.1, GE-Proton11-1), 2026-07-22. The
  `proxy run successful` from Nexus/STEP guides is not there.
- RadTux — experimental native Linux VFS for MO2:
  https://www.nexusmods.com/fallout4/mods/105285
- Wineserver selection under umu (T16): recorded `/proc/<pid>/environ` +
  `/proc/<pid>/exe` on three real launches (GE-Proton11-3, GE-Proton9-20,
  GE-Proton11-1) on the test install, 2026-08-22 — see the dedicated section
  above. Cross-referenced sources: no `WINESERVER` in the zipapp
  umu-launcher 1.4.1 and in the `proton` script of GE-Proton11-3; resolution
  auto-relative to the server by `ntdll.so`.
- pressure-vessel / Steam Runtime (the container that replaces `/usr` and makes the
  host wine unreachable):
  https://gitlab.steamos.cloud/steamrt/steam-runtime-tools/-/tree/main/pressure-vessel
- Engine log markers (T18): two complete X-Ray logs from real
  GAMMA installs (X-Ray Monolith 1.5.3, `'xrCore' build 9959`) — a session
  quit normally on 2026-08-13, a crashed session on 2026-08-26 — plus
  the format strings extracted from `anomaly/bin/AnomalyDX11.exe` (`strings`),
  which give literally what `xrDebugNew.cpp` can write. See the section
  "Post-mortem of session" above.
- Shader cache (T21): two real launches via `stalker-gamma-linux play`
  on `/mnt/games_samsung/Games/GAMMA` (GE-Proton11-3, AMD/Mesa GPU `radv`),
  2026-09-09 and 2026-09-14 — sizes of `cache/shaders/dxvk/*.dxvk.bin` and
  `cache/shaders/mesa/` recorded before/after each session, engine log
  (`xray_steamuser.log`) read to confirm a clean shutdown. Names and
  behavior by default of the environment variables: DXVK README
  (https://github.com/doitsujin/dxvk/blob/master/README.md), documentation
  Mesa (https://docs.mesa3d.org/envvars.html), NVIDIA driver README
  (https://download.nvidia.com/XFree86/Linux-x86_64/470.239.06/README/openglenvvariables.html) —
  verified on 2026-09-08 after finding that `DXVK_STATE_CACHE_PATH`,
  cited in several older guides, no longer corresponds to any
  variable read by current DXVK.
</content>
</invoke>
