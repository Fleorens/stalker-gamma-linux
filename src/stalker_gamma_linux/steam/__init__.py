"""Intégration Steam (T19) : GAMMA dans la bibliothèque, artwork compris.

T06 avait écarté l'écriture de `shortcuts.vdf` (format binaire non documenté,
comptes multiples, Steam à fermer) et renvoyait l'utilisateur vers *Ajouter un
jeu non-Steam*. Ce contournement est impossible **là où il compte le plus** :
en mode Gaming (Steam Deck, Bazzite, SteamOS), il n'y a pas de mode Bureau sous
la main. D'où ce module — les réserves de T06 restant valables, elles sont
devenues le cahier des charges : sauvegarde avant écriture, écriture atomique,
round-trip vérifié, préservation des raccourcis des autres, refus d'écrire
pendant que Steam tourne.

Découpage : `vdf` (le format, pur), `appid` (l'identifiant et l'artwork qui en
découle, pur), `entry` (notre raccourci dans le document, pur), `paths` (où
Steam vit), `running` (Steam tourne-t-il ?), `artwork` (les capsules du
paquet), `install` (l'écriture réelle), `session` (la commande utilisateur).
"""

from stalker_gamma_linux.steam.errors import (
    NoSteamAccountError,
    SteamError,
    SteamRunningError,
    SteamWriteError,
    VdfFormatError,
)
from stalker_gamma_linux.steam.install import (
    AccountResult,
    Action,
    add_shortcut,
    remove_shortcut,
)
from stalker_gamma_linux.steam.paths import SteamAccount, SteamInstall, discover_accounts
from stalker_gamma_linux.steam.session import run_steam_shortcut

__all__ = [
    "AccountResult",
    "Action",
    "NoSteamAccountError",
    "SteamAccount",
    "SteamError",
    "SteamInstall",
    "SteamRunningError",
    "SteamWriteError",
    "VdfFormatError",
    "add_shortcut",
    "discover_accounts",
    "remove_shortcut",
    "run_steam_shortcut",
]
