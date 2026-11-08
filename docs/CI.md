# CI (T10)

Three GitHub Actions workflows, each with a distinct role:

| Workflow | Trigger | Role |
|---|---|---|
| `ci.yml` | push on `main`, pull request | seven independent jobs (see below): lint/types/tests on a Python matrix, GUI smoke under Xvfb, real `install.sh` on four distributions, package build, secret scan, dependency audit, verification of advertised package names |
| `upstream-watch.yml` | daily cron, `workflow_dispatch` | detects a new revision of `Grokitach/Stalker_GAMMA` or `Mord3rca/gamma-launcher`; if so, runs a non-graphical subset of the pipeline in a container; opens an issue if it breaks |
| `release.yml` | tag `v*` | reruns the checks, publishes a GitHub Release (generated notes) — no more packaging artifact since the removal of Flatpak/AppImage (2026-07-26) |

No secret required: everything is public (repository, ModDB, GitHub releases), and the
only writes (committing the upstream state, creating an issue, publishing a
release) use the default `GITHUB_TOKEN` with permissions
explicitly scoped per job (`contents`/`issues` only where
needed — `contents: read` at the workflow level everywhere else).
`concurrency` cancels the obsolete `ci.yml` runs of the same `ref` (pushes
on a PR); `upstream-watch`/`release` do not cancel each other
a run in progress must not be killed by a second accidental trigger
while it commits or publishes).

Third-party actions are pinned by commit SHA (not by a moving tag,
CWE-1357/CWE-494); `.github/dependabot.yml` opens PRs every week
bump to the up-to-date SHA so these pins do not rot in place.

## `ci.yml`

Seven jobs, all independent except `build` (which waits for `test`):

### `test` — lint + types + tests

Real pitfall met while writing this job (validated in a container
`ubuntu:24.04` before committing): the `dev` extra of `pyproject.toml`
includes `PyGObject-stubs`, which declares a hard dependency on `PyGObject`
itself (confirmed via `pip show PyGObject-stubs`: `Requires: PyGObject,
typing_extensions`). Without system headers, `pip install ".[dev]"` fails to
compile `pycairo`/`PyGObject` (no manylinux wheel, see
`pyproject.toml`). Hence the step `apt-get install libcairo2-dev
libgirepository-2.0-dev gir1.2-gtk-4.0 gir1.2-adw-1 pkg-config` before
the Python install: `ruff`, `ruff format --check`, `mypy src` then `pytest -q`.

Matrix **Python 3.11 to 3.15**: the 3.14 was added because that is what
Fedora 44 and Arch shipped — so what a large part of users runs and
users and the dev machine. Its absence meant that "green CI" and
"it works on my machine" did not refer to the same thing. The 3.15 followed on
2026-11-07, afterwards: Fedora 45 shipped it and the install broke there (see
`install-script` below).

### `gui` — GTK4 smoke under Xvfb

`install.sh` eventually launches the GUI and the menu entry too, but its
~1360 lines of widgets were never imported in CI: the `test` job
only installs PyGObject for the `mypy` stubs, and `install-script` runs
deliberately without GTK. This job builds each screen for real, in a
venv `--system-site-packages` (PyGObject comes from the distro package, not from a
manylinux wheel — like on a user's machine), under a virtual X server
(`xvfb-run`), via `tests/test_gui_smoke.py`.

### `install-script` — the real installer on four distributions

`install.sh` is the entry point for 100 % of users (`curl | bash`)
and was never run anywhere but on the maintainer's Fedora, even though
the README promises "any Linux distribution". This job runs it for real
in Debian 12, Ubuntu 24.04, Fedora and Arch containers, and checks: the
GTK remedy shown is that of the right distribution (GTK is not
deliberately installed — the script must stop cleanly by
recommending the appropriate command), the venv/shortcuts/desktop entry are
in place, the installed CLI starts, and re-running the script is idempotent.

The first pass is done **without a compiler**, like on a player's machine. On
Fedora 45 (Python 3.15), `inflate64`, `pybcj` and `pyppmd` — pulled in by `py7zr`,
that `gamma-launcher` imports at load — have no wheel, and the
distribution does not package them: pip must compile them. The job then verifies
that `install.sh` stops on the distribution's remedy (`build_hint` of the
matrix, mirror of `INSTALL_COMMANDS["build-tools"]`), applies it
(`build_tools`) and reruns. The day upstream ships the wheels, the first
pass succeeds and this fallback no longer serves any purpose, with nothing to change.

### `build` — package build

`python -m build` (sdist + wheel), depends on `test`. Artifact kept
14 days.

### `secrets` — gitleaks

The project rules forbid any hard-coded secret; this job checks it at
place of relying on human review alone. `gitleaks` scans **the complete
history** (`fetch-depth: 0`), not just the working tree — a key
committed then removed stays exploitable as long as it is in the git objects
git. Binary pinned by version and verified by SHA-256 sum (not the action
official, which requires a license key for an organization repository).

### `deps` — pip-audit (non-blocking)

`constraints.txt` freezes the transitive closure, but freezing is not auditing:
a pinned version does not move when a security advisory lands on it.
This job installs the pinned closure (Python 3.11, the widest: `py7zr` only pulls
`backports.zstd` only under 3.14) and queries `pip-audit` on
the actually installed environment. `continue-on-error: true` for
now — to make it blocking when several weeks will be green in a row
and a written escape route will exist for unfixable alerts
upstream.

### `package-names` — do the advertised packages really exist?

Package names rot in silence (observed on 2026-08-16: `p7zip`
had disappeared from Fedora/Arch in favor of `7zip`, and `libunrar5t64` does not
exist on Debian 13. This job queries each distribution (Debian 12, Ubuntu
24.04, Fedora, Arch, non-free/multilib repositories enabled like the remedy
shown to the user) checks that the names extracted from
`environment/commands.py` really exist there. Installs nothing.

## `upstream-watch.yml`

### Status tracking

`Grokitach/Stalker_GAMMA` publishes **neither tags nor GitHub Releases** (verified
via the API: empty lists on both sides) — the only novelty signal is
the last commit of its default branch (`main`). `Mord3rca/gamma-launcher`
publishes real Releases (`v3.1` at the time of writing this, the same version
pinned in `pyproject.toml`). Hence two different mechanisms in
`scripts/check_upstream_state.py`:

- `stalker_gamma`: `GET /repos/Grokitach/Stalker_GAMMA/commits/main` → sha.
- `gamma_launcher`: `GET /repos/Mord3rca/gamma-launcher/releases/latest` →
  tag, then `GET .../tags` to resolve the sha of the matching commit.

The known state is committed in `.github/upstream-state.json` (preseeded with
the revisions actually validated during the development of T10:
`ab0f743a…` / `v3.1` @ `ade656e0…`) — **only** advanced if the job
of integration that follows has succeeded** (`report` job, success branch). A
upstream regression therefore leaves the state unchanged: the next day's run
re-detects and re-reports (comments the existing issue instead of recreating one
— label `upstream-regression`), instead of silently marking it as
"seen".

### Integration job: why a container, and why so little

`scripts/upstream_smoke_test.py` runs, on a minimal subset:

1. `doctor` (informational only — a CI container has no Steam or GPU,
   that is expected, never blocking here).
2. Fetching `modlist.txt` + `modpack_maker_list.txt` via
   `raw.githubusercontent.com` (a few tens of KB) — **not** the clone
   of `Grokitach/Stalker_GAMMA`, whose complete archive weighs **674 MB**
   (observed while testing: far too much for a daily check).
3. Parsing via `launcher.mods.read_mod_maker` — the real parser of
   gamma-launcher, to detect an upstream format regression.
4. Download + installation "dry run" (temporary directory) of 2
   ModDB mods (`--mod-count`), never the ~700 of the complete modpack: it is the
   most fragile path (ModDB + Cloudflare mirroring via `cloudscraper`),
   so the one worth verifying, but also the one where you must
   solicit ModDB the least (rate-limits). An `actions/cache` keeps the
   downloaded archives between runs, key on the sha of `Stalker_GAMMA`: a
   same revision retested (e.g. `workflow_dispatch --force` repeated) never
   taps ModDB again.

Two entries are explicitly excluded from the selection (`skip_names`/
`skip_titles` in the script): these are known ModDB placeholders
(empty/invalid archive) that `FullInstall._install_mods()` itself skips
always upstream (`gamma-launcher/launcher/commands/install.py`) — including
them without discernment would have failed the smoke test on a problem
already known and handled, not on a real regression (encountered for real while
testing: `FDDA Redone Fixes`, a 147-byte archive, breaks
the FOMOD installation with `AttributeError` before the exclusion).

The job runs in `container: image: ubuntu:24.04` (not just the runner
nu): `read_mod_maker`/archive extraction import `unrar` (ctypes) at
module load, which looks for `libunrar.so` — absent from a base image
and absent from `python:3.x-slim` (Debian, tested: `libunrar5` does not exist in
component enabled by default). `ubuntu:24.04` has `multiverse` enabled
by default and provides `libunrar5t64` there — **tested for real** (`ldconfig -p`
finds `libunrar.so.5`, `import unrar.unrarlib` succeeds) before writing the
workflow. Minimal system dependencies: `python3 python3-venv python3-pip
libunrar5 p7zip-full git curl ca-certificates` — no PyGObject/GTK here,
`doctor` never touches this path (`check_gtk_gui` is not in
`build_report`, see `environment/checks.py`).

Tested for real before committing (same commands as the workflow, in
a container `ubuntu:24.04` with real network access): the two mods
download from the real ModDB mirrors (Cloudflare included), extract
(zip + 7z), and `read_mod_maker` parses 486 entries of the real upstream
revision — see the project history for the complete output.

### Testable manually

`workflow_dispatch` with `force: true` runs the integration job even without
change detected (`changed` becomes `true` unconditionally) — useful
to check the complete chain, including opening an issue in case
of real failure, without waiting for a real upstream release.

## `release.yml`

A tag `v*`: reruns lint/types/tests (tags do not necessarily go
through a PR already verified by `ci.yml`, which only triggers on `main`),
checks that the tag matches `version` in `pyproject.toml` (fails before
publishing rather than letting a mislabeled release pass), then
publishes the GitHub Release. If `docs/release-notes/<tag>.md` exists, its
content becomes the notes (title = first `#`, rest of the file = body) —
the commit list generated by GitHub is for someone who already knows
the project, not the player discovering the release. Without this file,
`gh release create --generate-notes` takes over (auto-generated notes
from PRs/commits since the previous tag). No artifact to build
(the only distribution channel is `install.sh`, which clones the repo).

**History (T10, 2026-07-23)**: this workflow also built an
AppImage and a Flatpak bundle and attached them to the release
(`stalker-gamma-linux-x86_64.AppImage`, `org.stalkergammalinux.Gui.flatpak`
— tag `v0.1.0`, https://github.com/Fleorens/stalker-gamma-linux/releases/tag/v0.1.0).
These two jobs (`build-appimage`, `build-flatpak`) were removed on
2026-07-26 with the rest of the Flatpak/AppImage packaging (see
`docs/ARCHITECTURE.md` "Packaging: Flatpak/AppImage removed").

## What is not tested under real CI conditions

- Real Steam Deck / SteamOS: no access to a real SteamOS machine.
  The three workflows (`ci.yml`, `upstream-watch.yml` via
  `workflow_dispatch --force`, `release.yml` on a real tag) have, themselves,
  all run successfully on GitHub during the development of T10.
