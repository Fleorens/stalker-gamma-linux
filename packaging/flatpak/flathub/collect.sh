#!/usr/bin/env bash
# Stages the Flathub submission repo's expected root layout under
# flathub/org.stalkergammalinux.Gui/ — a copy, never pushed or PR'd (see
# README.md in this directory). Re-run after any manifest change.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
flatpak_dir="$(dirname "$here")"
dest="$here/org.stalkergammalinux.Gui"

rm -rf "$dest"
mkdir -p "$dest"

cp "$flatpak_dir"/org.stalkergammalinux.Gui.yml \
   "$flatpak_dir"/org.stalkergammalinux.Gui.metainfo.xml \
   "$flatpak_dir"/p7zip.yml \
   "$flatpak_dir"/umu-launcher.yml \
   "$flatpak_dir"/gamma-launcher.yml \
   "$flatpak_dir"/stalker-gamma-linux.yml \
   "$flatpak_dir"/python3-requirements.json \
   "$dest/"

echo "Staged Flathub submission layout at: $dest"
echo "(not pushed, not PR'd — see README.md)"
