#!/usr/bin/env bash
# Bootstrap stalker-gamma-linux : venv utilisateur (aucun sudo), installation
# du paquet, puis lancement de `stalker-gamma-linux install`.
#
# Curl-able :
#   curl -fsSL https://raw.githubusercontent.com/Fleorens/stalker-gamma-linux/main/install.sh | bash
#
# Ou, depuis un checkout existant :
#   ./install.sh [arguments passés à `install`, ex: --target /mnt/disque --shortcut]

set -euo pipefail

REPO_URL="https://github.com/Fleorens/stalker-gamma-linux.git"
APP_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/stalker-gamma-linux"
VENV_DIR="$APP_DATA_DIR/venv"
LOCAL_BIN="$HOME/.local/bin"

log() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }

# 1. Python >= 3.11, aucune installation système ici (juste une vérification).
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die \
    "python3 introuvable dans le PATH. Installe Python >= 3.11 avec le gestionnaire de ta distribution."

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION#*.}"
if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    die "Python >= 3.11 requis (trouvé $PYTHON_VERSION)."
fi
log "Python $PYTHON_VERSION détecté."

# 2. Source du paquet : le checkout courant si le script y est lancé depuis
#    l'intérieur, sinon clone/mise à jour d'un miroir sous $APP_DATA_DIR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SCRIPT_DIR" ] && grep -q '^name = "stalker-gamma-linux"' "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    SRC_DIR="$SCRIPT_DIR"
    log "Utilisation du checkout existant : $SRC_DIR"
else
    command -v git >/dev/null 2>&1 || die "git introuvable (nécessaire pour récupérer le dépôt)."
    SRC_DIR="$APP_DATA_DIR/src"
    if [ -d "$SRC_DIR/.git" ]; then
        log "Mise à jour du dépôt sous $SRC_DIR…"
        git -C "$SRC_DIR" pull --ff-only
    else
        log "Clonage de $REPO_URL sous $SRC_DIR…"
        mkdir -p "$APP_DATA_DIR"
        git clone --depth 1 "$REPO_URL" "$SRC_DIR"
    fi
fi

# 3. Venv utilisateur (jamais de site-packages système, jamais de sudo).
log "Venv sous $VENV_DIR…"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$SRC_DIR"

# `gamma-launcher` (dépendance de pyproject.toml) s'installe dans le même
# `$VENV_DIR/bin` que `stalker-gamma-linux`, mais ce venv n'est jamais activé
# ici : sans ceci, `stalker-gamma-linux` ne trouve pas `gamma-launcher` dans
# son PATH et échoue dès la première étape (`system.which("gamma-launcher")`
# cherche dans le PATH du process courant, pas dans `$VENV_DIR/bin`).
export PATH="$VENV_DIR/bin:$PATH"

# 4. Raccourci pratique si ~/.local/bin est déjà sur le PATH de l'utilisateur
#    (comme umu-run) : évite d'avoir à activer le venv à chaque fois.
mkdir -p "$LOCAL_BIN"
ln -sf "$VENV_DIR/bin/stalker-gamma-linux" "$LOCAL_BIN/stalker-gamma-linux"
case ":$PATH:" in
    *":$LOCAL_BIN:"*) log "Raccourci disponible : stalker-gamma-linux (via $LOCAL_BIN)" ;;
    *) log "Raccourci créé : $LOCAL_BIN/stalker-gamma-linux (ajoute $LOCAL_BIN à ton PATH)" ;;
esac

# 5. Vérification des prérequis *avant* le gros téléchargement (~90 Go) :
#    umu-launcher est le seul vrai bloquant (tout le reste — Proton-GE,
#    préfixe, verbs winetricks, DXVK — est ensuite automatique, sans sudo) ;
#    Steam/protontricks/7z/libunrar/Vulkan sont informatifs. Sauté si l'appel
#    ne visait que `--help`.
SKIP_DOCTOR=0
DOCTOR_TARGET_ARGS=()
prev=""
for arg in "$@"; do
    case "$arg" in
        -h | --help) SKIP_DOCTOR=1 ;;
    esac
    if [ "$prev" = "--target" ]; then
        DOCTOR_TARGET_ARGS=(--target "$arg")
    fi
    prev="$arg"
done

if [ "$SKIP_DOCTOR" -eq 0 ]; then
    log "Vérification des prérequis…"
    if ! "$VENV_DIR/bin/stalker-gamma-linux" doctor "${DOCTOR_TARGET_ARGS[@]}"; then
        printf '\033[1;33mAttention :\033[0m des prérequis système manquent (voir ci-dessus).\n'
        printf "L'installation va quand même pouvoir démarrer, mais peut échouer après avoir\n"
        printf 'déjà téléchargé plusieurs dizaines de Go si umu-launcher (ou un autre\n'
        printf 'prérequis bloquant) reste absent.\n'
        printf 'Continuer quand même ? [y/N] '
        if read -r reply 2>/dev/null </dev/tty; then
            case "$reply" in
                y | Y | yes | oui | o | O) ;;
                *) die "Installation annulée — corrige les prérequis ci-dessus puis relance." ;;
            esac
        else
            printf '\n'
            log "(pas de terminal interactif détecté — poursuite dans 5s, Ctrl-C pour annuler)"
            sleep 5
        fi
    fi
fi

# 6. Lance l'installation (les arguments du script lui sont transmis tels quels).
log "Lancement de l'installation…"
exec "$VENV_DIR/bin/stalker-gamma-linux" install "$@"
