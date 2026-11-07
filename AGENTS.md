# stalker-gamma-linux — shared rules for agents

This file is read by OpenCode (AGENTS.md) and by Claude Code (CLAUDE.md, a
symlink to this file). Single source of truth: only this file is edited.
The repository is **public**: nothing written here, in the code or in a commit
message may be confidential.

## Roles

- **OpenCode**, on the aibox's local model: writes the code. In a job, it
  works alone in a worktree, on a `gen/<id>-*` branch.
- **Claude Code**: reviews, fixes, decides. Nothing reaches `main` without
  review: automatic merge when the checks and Claude Code's review pass,
  otherwise by Florian (`dev merge`).

## Language

- Everything written for an agent (this file, task sheets, briefs) is in
  English. Code, comments, docstrings, test names and commit messages too.
- Your final report (job summary) is in **French**: Florian reads it.

## Rules

- Never `git push`, never rewrite history, never commit on `main`.
- Small, atomic commits, in Conventional Commits format, **in English**:
  `type(scope): description` — types `feat`, `fix`, `perf`, `refactor`, `test`,
  `docs`, `style`, `chore`, `ci`; scope = module touched (`prefix`, `gui`,
  `engine`, `doctor`…); `!` after the scope for a breaking change.
  Example: `fix(verify): a missing archive is not a corruption`.
- Before finishing: run `bash .devbox/check` and fix until it passes.
- No dependency added without a justification in the commit message.
- Never build artifacts, binaries or large files in git.
- Ambiguity: pick the simplest, reversible option and explain it in the
  commit.

## Project

Linux integration layer to install and launch S.T.A.L.K.E.R. G.A.M.M.A.:
Proton prefix (GE-Proton, umu), Mod Organizer 2 under Proton, desktop and
Steam shortcuts, diagnostics. Downloading and installing the mods is
delegated to the `gamma-launcher` engine, called as a subprocess.

- **Stack**: Python ≥ 3.11 (the code must run on 3.11: `ruff` and `mypy`
  target 3.11), `argparse` CLI, `rich` output, GTK4/libadwaita GUI through the
  **distribution's** PyGObject.
- **Layout**:
  - `src/stalker_gamma_linux/`: one subpackage per domain (`engine`, `prefix`,
    `mo2`, `steam`, `desktop`, `integrity`, `backups`, `postmortem`,
    `environment`, `gui`); `cli.py` and `orchestrator.py` assemble them.
  - `tests/`: pytest, one file per module (`test_<module>.py`).
  - `docs/ARCHITECTURE.md`: the settled decisions, one section per topic
    (still in French). Read the section that concerns your task, not the whole
    file (it is 1,600 lines long).
  - `tasks/Txx-*.md`: the task sheets; `tasks/README.md` their status.
- **Verify**: `bash .devbox/check` = `ruff check`, `ruff format --check`,
  `mypy src` (strict), then `pytest` under `xvfb-run` (GUI test included).
  It is the `test` + `gui` job of `.github/workflows/ci.yml`.
- **Format**: `ruff format .` then `ruff check --fix .`.

### Conventions

- Comments, docstrings and test names in English. Existing French ones are
  translated when the surrounding code is touched, never in a separate sweep.
  A comment says **why** (the constraint, the pitfall observed), not what the
  line does.
- User-facing strings: in English, wrapped in `_()` (`i18n.py`). After adding
  or changing some: `make update-messages`, translate in
  `locale/fr/.../*.po`, then `make compile-messages`; the `.mo` is versioned.
- GUI: **no business logic** in `gui/`. It calls the same functions as the
  CLI, through `output.Reporter` and the progress callbacks. The pure modules
  of `gui/` (`viewmodel`, `worker`, `prefs`, `phases`, `space`, `summary`,
  `format`) do not import `gi`.
- Deleting files or directories: always through the guards of
  `paths_safety.py`, never a bare `shutil.rmtree` on a computed path.
- Dependencies: declared in `pyproject.toml` with an upper bound, and the
  exact closure pinned in `constraints.txt` (procedure at the top of the
  file). `gamma-launcher` is pinned by commit SHA, the GitHub actions too.
- Tests: no network access nor call to the real `gamma-launcher` outside the
  `network` marker, excluded by default. System commands (`umu-run`, `wine`,
  `steam`…) are mocked.

### Devbox limits

The devbox is a container with no screen, no GPU, no Steam nor Proton: no real
GAMMA install, no `play`, no MO2 runs there. A behaviour that can only be
checked in game or on screen is validated by Florian on his machine: flag it
in your report instead of declaring it verified.

### Environment (devbox)

The main clone's venv serves every worktree (`.devbox/check` finds it on its
own). Recreate it after a dependency change, as user `dev`, never as root:

```
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -c constraints.txt -e ".[dev]"
```

`--system-site-packages` to see Debian's PyGObject; pip still builds a newer
one, required by `PyGObject-stubs` (hence `python3-dev`,
`libgirepository-2.0-dev` and `libcairo2-dev` on the system side).

### Security

- Audit reports (`audits/`) are never versioned: they describe vulnerabilities
  before the fix. A fix's commit message describes the vulnerability once
  closed, without a how-to.
- No hard-coded secret: `gitleaks` scans the whole history in CI.
