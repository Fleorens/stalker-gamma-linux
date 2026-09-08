"""Identifiant d'un raccourci non-Steam, et noms de fichiers d'artwork qui en découlent.

**Ce qui a été vérifié sur la machine** (Steam natif, relevé le 2026-09-08),
parce que les formules qui circulent sur le web ne s'accordent pas :

1. Le `shortcuts.vdf` réel porte `appid = -915409416`, soit `0xC96FF5F8` non
   signé. **Aucune** des formules courantes ne le reproduit —
   `crc32(Exe + AppName) | 0x80000000` en tête, testée avec et sans les
   guillemets d'`Exe`, dans les deux ordres, sur le chemin actuel comme sur le
   chemin d'origine.
2. `logs/console_log.txt` explique pourquoi : `sanitize shortcut app id
   "<exe>": replacing 0 with 3379557880, reason: k_unAppIdInvalid`. Steam
   n'*applique* pas une formule, il **remplace un identifiant invalide (0)** par
   une valeur de son choix. Deux relevés de ce message, sur deux exécutables
   différents, ne se laissent réduire à aucun CRC de leur chemin.
3. Steam ne recalcule **pas** l'identifiant d'une entrée existante : celui du
   fichier réel a survécu à un déplacement de l'exécutable (le `Exe` du
   `shortcuts.vdf` ne pointe plus sur le chemin cité par le journal, l'`appid`
   n'a pas bougé).

D'où la règle suivie ici, qui n'a rien d'un pari : **on écrit nous-mêmes un
identifiant valide**, et on nomme l'artwork d'après lui. Laisser le champ à 0
pour que Steam « choisisse » serait au contraire un pari perdu d'avance — la
valeur choisie est imprévisible, et les fichiers d'artwork posés à l'avance ne
correspondraient à rien. Quand une entrée existe déjà, on **reprend son
identifiant** au lieu d'en imposer un (point 3 : Steam le garde, nous aussi).

La formule retenue pour une entrée neuve est le CRC32 historique. Non pas
parce que Steam la partage — le point 1 dit le contraire — mais parce qu'il
faut *une* valeur, et qu'elle doit être **déterministe** : recréer le raccourci
après avoir supprimé `shortcuts.vdf` doit retomber sur le même identifiant, donc
sur l'artwork déjà posé, au lieu d'accumuler des fichiers orphelins dans `grid/`.

Signé/non signé, l'autre piège : le VDF stocke un entier 32 bits **signé** (le
bit de poids fort à 1 rend la valeur négative), tandis que les noms de fichiers
d'artwork et les journaux Steam utilisent la forme **non signée** de ces mêmes
32 bits. Les deux conversions sont ici, et nulle part ailleurs.
"""

from __future__ import annotations

import zlib

# Bit de poids fort à 1 : marque les identifiants « hors bibliothèque Steam ».
# Toutes les valeurs observées sur la machine le portent.
_NON_STEAM_FLAG = 0x80000000
_UINT32_MASK = 0xFFFFFFFF
_SIGN_THRESHOLD = 0x80000000


def to_unsigned(signed_value: int) -> int:
    """Les 32 bits de `signed_value` lus comme un entier non signé (nom d'artwork)."""
    return signed_value & _UINT32_MASK


def to_signed(unsigned_value: int) -> int:
    """Les 32 bits de `unsigned_value` lus comme un entier signé (champ `appid` du VDF)."""
    masked = unsigned_value & _UINT32_MASK
    return masked - (1 << 32) if masked >= _SIGN_THRESHOLD else masked


def derive_appid(exe: str, app_name: str) -> int:
    """Identifiant non signé pour une entrée neuve. Déterministe (voir le docstring)."""
    return (zlib.crc32((exe + app_name).encode("utf-8")) | _NON_STEAM_FLAG) & _UINT32_MASK


def is_valid_appid(signed_value: int) -> bool:
    """`False` pour un identifiant que Steam remplacerait (0), donc inutilisable pour l'artwork."""
    return to_unsigned(signed_value) != 0


def next_free_appid(exe: str, app_name: str, taken: frozenset[int]) -> int:
    """Premier identifiant non signé libre à partir de `derive_appid`.

    `taken` = les identifiants déjà employés par les autres raccourcis du
    fichier. Une collision est improbable mais pas impossible, et deux entrées
    partageant un identifiant partageraient aussi leur artwork et leur
    configuration manette — on décale plutôt que d'écraser le voisin.
    """
    candidate = derive_appid(exe, app_name)
    while candidate in taken:
        candidate = ((candidate + 1) & _UINT32_MASK) | _NON_STEAM_FLAG
    return candidate
