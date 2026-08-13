"""Feral GameMode : optimisations système appliquées le temps d'une partie.

GameMode (`gamemoded`) bascule le gouverneur CPU en `performance`, relève la
priorité du processus et pousse le GPU en mode perf tant qu'un jeu tourne —
gratuit sur une machine où le paquet est déjà installé, ce qui est le cas par
défaut sur Nobara, CachyOS, Bazzite et le Steam Deck.

**Pourquoi `gamemoderun` et pas un daemon activé en permanence.** Le service
est *activé à la demande* par D-Bus (`com.feralinteractive.GameMode`, unité
`Type=dbus`) : tant qu'aucun jeu ne l'a réclamé, `gamemoded -s` répond
« inactive », et c'est le fonctionnement nominal — pas une panne à réparer avec
un `systemctl --user enable`. Il n'y a donc rien à *démarrer* : il faut un
client qui *demande* le mode, et c'est exactement ce que fait `gamemoderun`.

**Comment ça marche.** `gamemoderun` est le script officiel du paquet : il
ajoute `libgamemodeauto.so.0` au `LD_PRELOAD` puis exec la commande. La
bibliothèque réclame le mode à son chargement et le relâche à la sortie du
processus. C'est le mécanisme exact de l'option de lancement Steam
`gamemoderun %command%`. Le `LD_PRELOAD` se propage aux enfants (umu-run →
runtime conteneurisé → wine → l'exécutable du jeu), donc **envelopper
`umu-run` suffit** : inutile d'atteindre le processus du jeu au fond de la
pile, et les demandes multiples sont comptées par le daemon.

**Best effort assumé.** La soname est donnée sans chemin : c'est l'éditeur de
liens qui choisit la bonne architecture, et s'il ne trouve rien (paquet 32 bits
absent pour les processus wow64), il émet un avertissement et continue — jamais
d'échec de lancement. On ne vérifie donc rien de plus ici : GameMode absent =
on lance le jeu tel quel, sans bruit ni erreur.

**Le piège du groupe `gamemode`.** Fedora et Arch livrent une règle polkit
(`/usr/share/polkit-1/rules.d/gamemode.rules`) qui n'autorise `cpugovctl` et
`gpuclockctl` **qu'aux membres du groupe `gamemode`** ; l'action elle-même est
en `allow_active: no`. Sans ce groupe, le daemon tourne, le mode est bien
« active », mais chaque changement de gouverneur CPU échoue en silence côté
utilisateur (`pkexec … Not authorized` dans le journal, `gamemoded -t` échoue
sur « Verifying CPU governor setting »). Il reste les priorités I/O et
l'ordonnancement — la moitié du bénéfice. C'est invisible sans aller lire
`journalctl`, donc `group_status` le détecte et `doctor` le dit, avec le
`usermod` qui va bien. Un système sans groupe `gamemode` (politique polkit
permissive) ne déclenche rien : il n'y a rien à corriger.
"""

from __future__ import annotations

import grp
import os
import pwd
from collections.abc import Sequence
from enum import Enum, auto

from stalker_gamma_linux.environment import system

GAMEMODE_RUN = "gamemoderun"
GAMEMODE_GROUP = "gamemode"


class GroupStatus(Enum):
    """État de l'appartenance au groupe `gamemode` de la session courante."""

    # Pas de groupe `gamemode` sur ce système : la règle polkit qui s'appuie
    # dessus n'existe pas non plus — rien à corriger.
    NOT_APPLICABLE = auto()
    MEMBER = auto()
    # Ajouté au groupe, mais la session en cours a été ouverte avant : les gids
    # d'une session sont figés à l'ouverture, il faut se reconnecter.
    NEEDS_RELOGIN = auto()
    MISSING = auto()


def find_gamemoderun() -> str | None:
    """Chemin de `gamemoderun` dans le PATH, ou None si GameMode n'est pas installé."""
    return system.which(GAMEMODE_RUN)


def is_available() -> bool:
    return find_gamemoderun() is not None


def group_status() -> GroupStatus:
    """Appartenance au groupe `gamemode`, qui conditionne le gouverneur CPU.

    On regarde les gids **de la session courante** (`os.getgroups`) et pas
    seulement la liste du groupe : c'est ce que verra le processus du jeu, et
    c'est ce qui distingue « pas dans le groupe » de « ajouté mais pas encore
    reconnecté » — deux problèmes aux remèdes différents.
    """
    try:
        entry = grp.getgrnam(GAMEMODE_GROUP)
    except KeyError:
        return GroupStatus.NOT_APPLICABLE
    if entry.gr_gid in os.getgroups():
        return GroupStatus.MEMBER
    return GroupStatus.NEEDS_RELOGIN if _current_user() in entry.gr_mem else GroupStatus.MISSING


def _current_user() -> str:
    """Nom de l'utilisateur courant, par uid — pas par terminal.

    `os.getlogin()` lit le propriétaire du terminal de contrôle : il échoue sans
    tty (lancement depuis l'entrée de menu, service systemd) et peut mentir sous
    `sudo`. L'uid effectif est le seul repère fiable ici.
    """
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:  # uid absent de /etc/passwd (conteneur minimal)
        return os.environ.get("USER", "")


def wrap(command: Sequence[str]) -> list[str]:
    """`[gamemoderun, *command]` si GameMode est installé, sinon la commande inchangée.

    Retourne toujours une nouvelle liste : l'appelant garde sa commande d'origine
    intacte (et peut la journaliser telle quelle).
    """
    binary = find_gamemoderun()
    if binary is None:
        return list(command)
    return [binary, *command]
