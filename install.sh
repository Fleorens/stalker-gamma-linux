#!/usr/bin/env bash
# Bootstrap stalker-gamma-linux : monte l'environnement natif (aucun sudo) et
# lance la GUI d'installation — « the S.T.A.L.K.E.R. G.A.M.M.A. installation
# experience », en une commande, sur ta machine (pas dans un bac à sable).
#
# Pourquoi natif et pas un bac à sable (Flatpak/AppImage) : l'outil orchestre
# Wine/Proton, umu, libunrar, Steam, la stack 32-bit… tout ce que ta
# distribution a déjà. Un sandbox devrait ré-embarquer/contourner chacun de
# ces éléments ; en natif la GUI les utilise directement.
#
# Curl-able :
#   curl -fsSL https://raw.githubusercontent.com/Fleorens/stalker-gamma-linux/main/install.sh | bash
#
# Options :
#   --no-launch   monte tout (venv, raccourci) mais ne lance pas la GUI

set -euo pipefail

REPO_URL="https://github.com/Fleorens/stalker-gamma-linux.git"
APP_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/stalker-gamma-linux"
VENV_DIR="$APP_DATA_DIR/venv"
LOCAL_BIN="$HOME/.local/bin"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"

log() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die() { printf '\033[1;31mErreur :\033[0m %s\n' "$*" >&2; exit 1; }

NO_LAUNCH=0
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --no-launch) NO_LAUNCH=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h | --help)
            printf 'Usage : install.sh [--no-launch] [--uninstall]\n'
            printf '  monte le venv + le raccourci, puis lance la GUI (sauf --no-launch).\n'
            printf '  --uninstall retire tout ce que ce script a posé (le jeu est conservé).\n'
            exit 0
            ;;
    esac
done

# Désinstallation : on délègue d'abord à la CLI (raccourcis, réglages, état,
# journaux — elle sait exactement ce qu'elle a écrit), puis on retire le venv,
# que la CLI ne peut pas supprimer puisqu'elle tourne depuis lui. Les données de
# jeu ne sont jamais touchées ici : `stalker-gamma-linux uninstall --game-data`
# est le seul chemin qui les efface, et il faut le demander explicitement.
if [ "$UNINSTALL" -eq 1 ]; then
    if [ -x "$VENV_DIR/bin/stalker-gamma-linux" ]; then
        "$VENV_DIR/bin/stalker-gamma-linux" uninstall --no-venv-hint || \
            warn "Le nettoyage par la CLI a échoué — on retire quand même le venv."
    else
        warn "Aucune installation détectée sous $VENV_DIR — nettoyage des raccourcis seulement."
        rm -f "$LOCAL_BIN/stalker-gamma-linux" "$LOCAL_BIN/stalker-gamma-linux-gui"
        rm -f "$APPLICATIONS_DIR/stalker-gamma-linux-gui.desktop"
    fi
    rm -rf "$APP_DATA_DIR"
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
    log "Désinstallation terminée. Les données de jeu, elles, sont intactes."
    exit 0
fi

# Commande d'installation du stack GTK selon la distribution (le seul prérequis
# système de la GUI native ; PyGObject n'a pas de roue pip, il vient du paquet
# distro). Miroir de `environment.commands` INSTALL_COMMANDS["gtk-gui"].
gtk_install_hint() {
    local ids=""
    # shellcheck disable=SC1091
    [ -r /etc/os-release ] && ids="$(. /etc/os-release 2>/dev/null && echo "${ID:-} ${ID_LIKE:-}")"
    case " $ids " in
        *fedora*|*rhel*|*centos*|*nobara*) echo "sudo dnf install gtk4 libadwaita python3-gobject" ;;
        *arch*|*manjaro*|*endeavouros*|*cachyos*|*steamos*) echo "sudo pacman -S gtk4 libadwaita python-gobject" ;;
        *debian*|*ubuntu*|*pop*|*linuxmint*) echo "sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi" ;;
        *) echo "installe gtk4 + libadwaita + les bindings Python (PyGObject) via ton gestionnaire de paquets" ;;
    esac
}

# 1. Python >= 3.11 (vérification seule, aucune installation système).
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

# 2. Source : le checkout courant si le script y est lancé depuis l'intérieur,
#    sinon clone/mise à jour d'un miroir sous $APP_DATA_DIR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SCRIPT_DIR" ] && grep -q '^name = "stalker-gamma-linux"' "$SCRIPT_DIR/pyproject.toml" 2>/dev/null; then
    SRC_DIR="$SCRIPT_DIR"
    log "Utilisation du checkout existant : $SRC_DIR"
else
    command -v git >/dev/null 2>&1 || die "git introuvable (nécessaire pour récupérer le dépôt)."
    SRC_DIR="$APP_DATA_DIR/src"
    if [ -d "$SRC_DIR/.git" ]; then
        # `pull --ff-only` échouait dès que l'amont avait été rebasé ou
        # force-pushé : l'historique tronqué d'un clone --depth 1 n'a alors
        # aucun ancêtre commun, et `set -e` arrêtait net le script en laissant
        # l'utilisateur bloqué sans remède. Ce miroir appartient à l'outil et
        # ne contient jamais de commit local : on se réaligne sur l'amont sans
        # état d'âme, et on re-clone proprement si même ça échoue.
        log "Mise à jour du dépôt sous $SRC_DIR…"
        BRANCH="$(git -C "$SRC_DIR" symbolic-ref --short HEAD 2>/dev/null || echo main)"
        if ! { git -C "$SRC_DIR" fetch --depth 1 origin "$BRANCH" >/dev/null 2>&1 &&
               git -C "$SRC_DIR" reset --hard FETCH_HEAD >/dev/null 2>&1; }; then
            warn "Mise à jour impossible — re-clonage propre du dépôt…"
            rm -rf "$SRC_DIR"
            git clone --depth 1 "$REPO_URL" "$SRC_DIR" \
                || die "Clonage de $REPO_URL impossible (réseau ? dépôt inaccessible ?)."
        fi
    else
        log "Clonage de $REPO_URL sous $SRC_DIR…"
        mkdir -p "$APP_DATA_DIR"
        git clone --depth 1 "$REPO_URL" "$SRC_DIR" \
            || die "Clonage de $REPO_URL impossible (réseau ? dépôt inaccessible ?)."
    fi
fi

# 3. Venv utilisateur AVEC --system-site-packages : PyGObject (GTK4/libadwaita)
#    n'a pas de roue pip (extension liée au GObject-introspection du système) ;
#    il doit venir du paquet distro, donc le venv doit voir les site-packages
#    système. Aucun sudo, aucune écriture hors du home.
log "Venv (--system-site-packages) sous $VENV_DIR…"
"$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$SRC_DIR"

# `gamma-launcher` (dépendance) s'installe dans $VENV_DIR/bin ; ce venv n'est
# jamais activé → on l'ajoute au PATH pour que la GUI le trouve.
export PATH="$VENV_DIR/bin:$PATH"

# 4. Raccourcis en ligne de commande (GUI + CLI de debug) si ~/.local/bin est
#    sur le PATH.
mkdir -p "$LOCAL_BIN"
ln -sf "$VENV_DIR/bin/stalker-gamma-linux-gui" "$LOCAL_BIN/stalker-gamma-linux-gui"
ln -sf "$VENV_DIR/bin/stalker-gamma-linux" "$LOCAL_BIN/stalker-gamma-linux"

# 4bis. umu-launcher : LE prérequis sans paquet Fedora/Debian (pas de PyPI non
#       plus). On l'installe nous-mêmes — zipapp officiel ~420 Kio déposé dans
#       ~/.local/bin, sans sudo. Non fatal : la GUI a un bouton « Installer »
#       dans son Diagnostic si le réseau manque ici.
if ! command -v umu-run >/dev/null 2>&1 && [ ! -x "$LOCAL_BIN/umu-run" ]; then
    log "umu-launcher absent — installation automatique (zipapp officiel)…"
    "$VENV_DIR/bin/stalker-gamma-linux" install-umu \
        || warn "Installation d'umu-launcher impossible (réseau ?) — la GUI proposera de réessayer."
fi

# 5. Entrée bureau : l'appli apparaît dans le menu (« Lanceur GAMMA (Linux) »)
#    pour les lancements suivants. Exec en chemin absolu (indépendant du PATH du
#    menu, souvent minimal). Icône embarquée dans le paquet. C'est la SEULE
#    entrée créée par ce script : le raccourci optionnel de la GUI/CLI
#    (desktop/entry.py, « Jouer à GAMMA (direct) ») ne se recoupe jamais avec
#    celle-ci (nom et fichier distincts) — voir gui/prefs.py.
ICON_SRC="$("$VENV_DIR/bin/python" -c 'import importlib.resources as r; print(r.files("stalker_gamma_linux") / "assets" / "icon.png")' 2>/dev/null || true)"
mkdir -p "$APPLICATIONS_DIR"
if [ -n "$ICON_SRC" ] && [ -f "$ICON_SRC" ]; then
    mkdir -p "$ICON_DIR"
    cp -f "$ICON_SRC" "$ICON_DIR/stalker-gamma-linux-gui.png"
fi
cat > "$APPLICATIONS_DIR/stalker-gamma-linux-gui.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=GAMMA Linux Launcher
Name[fr]=Lanceur GAMMA (Linux)
GenericName=S.T.A.L.K.E.R. GAMMA installer & launcher
GenericName[fr]=Installeur et lanceur S.T.A.L.K.E.R. GAMMA
Comment=Install, manage and launch S.T.A.L.K.E.R. G.A.M.M.A. on Linux
Comment[fr]=Installe, gère et lance S.T.A.L.K.E.R. G.A.M.M.A. sous Linux
Exec=$VENV_DIR/bin/stalker-gamma-linux-gui
Icon=stalker-gamma-linux-gui
Categories=Game;
Terminal=false
StartupNotify=true
StartupWMClass=org.stalkergammalinux.Gui
DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -qtf "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true

case ":$PATH:" in
    *":$LOCAL_BIN:"*) log "Raccourcis prêts (commande + menu applications : « Lanceur GAMMA »)." ;;
    *) warn "Ajoute $LOCAL_BIN à ton PATH pour la commande ; l'entrée du menu, elle, marche déjà." ;;
esac

# 6. Pré-vol GTK : PyGObject/GTK4/libadwaita doivent être présents pour la GUI.
if ! "$VENV_DIR/bin/python" - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa
PY
then
    warn "GTK4 / libadwaita / PyGObject manquants — la GUI ne peut pas s'ouvrir sans eux."
    printf '  Installe-les :\n    %s\n' "$(gtk_install_hint)"
    printf '  Puis relance ce script, ou clique « Lanceur GAMMA » dans ton menu.\n'
    exit 0
fi

# 7. Lancement de la GUI d'installation (sauf --no-launch). La fenêtre guide le
#    reste : diagnostic des prérequis, choix de la cible, installation.
if [ "$NO_LAUNCH" -eq 1 ]; then
    log "Prêt. Lance « Lanceur GAMMA » (menu) ou : stalker-gamma-linux-gui"
    exit 0
fi
log "Lancement de l'installeur GAMMA…"
exec "$VENV_DIR/bin/stalker-gamma-linux-gui"
