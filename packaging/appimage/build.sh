#!/usr/bin/env bash
# Builds packaging/appimage/dist/stalker-gamma-linux-x86_64.AppImage from the
# current checkout. Self-contained: bootstraps its own tool venv, builds its
# own p7zip, fetches its own umu-run — nothing needs to pre-exist on the
# machine beyond Python 3, a C++ toolchain and network access. See
# docs/PACKAGING.md for what's bundled and why.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
APPDIR_SRC="$HERE/stalker-gamma-linux"
CACHE="$HERE/.cache"
BUILD="$HERE/.build"
DIST="$HERE/dist"
TOOL_VENV="$HERE/.tool-venv"

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
P7ZIP_VERSION="17.05"
P7ZIP_SHA256="d2788f892571058c08d27095c22154579dfefb807ebe357d145ab2ddddefb1a6"
UMU_VERSION="1.4.1"
UMU_SHA256="97b6ff2981912a6b9cd223ec4fb5c4e0a819e5c166811e0f82ae60fad0801c21"

mkdir -p "$CACHE" "$BUILD" "$DIST"

echo "==> Tool venv (python-appimage)"
if [ ! -x "$TOOL_VENV/bin/python-appimage" ]; then
  python3 -m venv "$TOOL_VENV"
  "$TOOL_VENV/bin/pip" install --quiet --upgrade pip python-appimage
fi

echo "==> p7zip $P7ZIP_VERSION (7z/7za/7zr, built from source — see packaging/flatpak/p7zip.yml for the licensing rationale, identical here)"
if [ ! -x "$CACHE/p7zip-$P7ZIP_VERSION/bin/7z" ]; then
  curl -sL -o "$CACHE/p7zip-$P7ZIP_VERSION.tar.gz" \
    "https://github.com/p7zip-project/p7zip/archive/refs/tags/v${P7ZIP_VERSION}.tar.gz"
  echo "$P7ZIP_SHA256  $CACHE/p7zip-$P7ZIP_VERSION.tar.gz" | sha256sum -c -
  tar xzf "$CACHE/p7zip-$P7ZIP_VERSION.tar.gz" -C "$CACHE"
  make -C "$CACHE/p7zip-$P7ZIP_VERSION" -j"$(nproc)" all3
fi

echo "==> umu-launcher $UMU_VERSION (official self-contained zipapp)"
if [ ! -f "$CACHE/umu-run" ]; then
  curl -sL -o "$CACHE/umu-launcher-zipapp.tar" \
    "https://github.com/Open-Wine-Components/umu-launcher/releases/download/${UMU_VERSION}/umu-launcher-${UMU_VERSION}-zipapp.tar"
  echo "$UMU_SHA256  $CACHE/umu-launcher-zipapp.tar" | sha256sum -c -
  tar xf "$CACHE/umu-launcher-zipapp.tar" -C "$CACHE"
  cp "$CACHE/umu/umu-run" "$CACHE/umu-run"
fi

echo "==> Staging \$APPDIR/usr extras"
rm -rf "$BUILD/usr"
mkdir -p "$BUILD/usr/bin"
(cd "$CACHE/p7zip-$P7ZIP_VERSION" && ./install.sh \
  "$BUILD/usr/bin" "$BUILD/usr/lib/p7zip" "$BUILD/usr/share/man" "$BUILD/usr/share/doc/p7zip")
install -Dm755 "$CACHE/umu-run" "$BUILD/usr/bin/umu-run"
ln -sf umu-run "$BUILD/usr/bin/umu_run.py"

echo "==> requirements.txt (gitignored, regenerated every build)"
cp "$APPDIR_SRC/requirements.txt.in" "$APPDIR_SRC/requirements.txt"
echo "$REPO_ROOT" >> "$APPDIR_SRC/requirements.txt"

echo "==> python-appimage build app"
(
  cd "$DIST"
  "$TOOL_VENV/bin/python-appimage" build app \
    -p "$PYTHON_VERSION" \
    "$APPDIR_SRC" \
    -x "$BUILD/usr"
)
rm -f "$APPDIR_SRC/requirements.txt"

echo "==> Done: $DIST/stalker-gamma-linux-$(uname -m).AppImage"
