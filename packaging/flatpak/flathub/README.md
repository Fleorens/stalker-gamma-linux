# Flathub submission — prepared, not submitted

Flathub publishes from a dedicated repo (`github.com/flathub/<app-id>`) whose
**root** holds the manifest and its module files — no different from
`packaging/flatpak/` in this repo. Nothing here has been pushed or opened as
a PR; this directory is the staged content plus a checklist, so submitting
later is a copy + `git push`, not a rewrite.

## Prepare the staging copy

```sh
./collect.sh
```

Copies the manifest, module files, `python3-requirements.json` and the
metainfo into `flathub/org.stalkergammalinux.Gui/` (gitignored — regenerated
from the canonical files in `packaging/flatpak/`, never hand-edited there).

## To actually submit (not done)

1. Fork/clone `https://github.com/flathub/flathub`, create branch
   `new-app/org.stalkergammalinux.Gui` (per Flathub's submission process —
   check their current docs, this changes over time).
2. Copy `org.stalkergammalinux.Gui/*` from the staging dir into that branch's
   root.
3. Open a PR against `flathub/flathub`; their CI builds the manifest and
   flags issues (network access during build, missing licenses, etc.).
4. Once merged, Flathub creates `github.com/flathub/org.stalkergammalinux.Gui`
   and future updates go there directly (new PRs bump `tag`/`commit` in
   `gamma-launcher.yml`, the `dir` source in `stalker-gamma-linux.yml` is
   swapped for a versioned `git`/`archive` source pinned to a release tag —
   Flathub does not accept `type: dir` against a live working tree).

## Pre-submission checklist

- [x] `appstreamcli validate` passes on the metainfo (0 warnings/errors).
- [x] Builds clean with `flatpak-builder` (network disabled at module build
      time — all Python deps are pre-resolved wheels in
      `python3-requirements.json`, not fetched from PyPI during the build).
- [x] No proprietary or game/mod data bundled (see docs/PACKAGING.md,
      "What's deliberately not bundled").
- [ ] `stalker-gamma-linux.yml`'s `dir` source needs to become a pinned
      `git`/`archive` source before this can be submitted for real — Flathub
      builds must be reproducible from a fixed ref, not "whatever is on disk
      right now". Left as `dir` intentionally for local iteration
      (`make package-flatpak` always packages the current checkout).
- [ ] Icon: 512×512 PNG works, but Flathub prefers a scalable (SVG) app icon
      when available. GAMMA's logo (`assets/gamma-logo.png`) is a raster
      banner (see memory/project notes) — would need a redrawn SVG mark, out
      of scope here.
- [ ] Screenshots for the metainfo `<screenshots>` block (none included yet).
