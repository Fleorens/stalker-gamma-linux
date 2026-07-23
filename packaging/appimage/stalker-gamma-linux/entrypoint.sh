#!/bin/bash
# $APPDIR/usr/bin holds our bundled umu-run + 7z (see build.sh) — the base
# Python AppImage's own AppRun would have put it on PATH, but supplying a
# custom entrypoint (this file) replaces that AppRun outright, so we redo it
# here. Without this, environment.checks' system.which() lookups for
# "umu-run"/"7z" would silently fail even though the files are right there.
export PATH="$APPDIR/usr/bin:$PATH"
# Not "python -m stalker_gamma_linux.cli": that module has no
# `if __name__ == "__main__": main()` guard (by design — it's meant to be
# reached through the pip-generated console-script entry point, never run
# directly), so `-m` would import it and exit 0 without calling main() at
# all. Call the entry point pip already generated instead.
"$APPDIR/usr/bin/stalker-gamma-linux" "$@"
