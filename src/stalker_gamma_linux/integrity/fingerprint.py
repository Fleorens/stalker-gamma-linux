"""Ce qui permet d'affirmer « ce fichier n'a pas bougé » sans le relire.

Un scan complet de `gamma/mods/` lit ~83 Gio : plusieurs minutes, à chaque
appel, y compris quand rien n'a bougé depuis la veille. La référence au format
`md5sum` ne portait que le hash et le chemin — `scan_tree` n'avait donc
strictement aucun moyen de le savoir, et rehachait tout. `FileStat` est ce
moyen : la taille et la date de modification en nanosecondes, c'est-à-dire ce
que le noyau connaît déjà de chaque fichier et qu'un `stat()` rend sans lire un
seul octet de son contenu.

**Ce que le court-circuit garantit, et ce qu'il ne garantit pas.** Les avaries
que ce paquet cherche passent toutes par une écriture ordinaire — disque plein
qui tronque, autre outil qui écrase, extraction interrompue — et une écriture
ordinaire déplace la taille ou la mtime. Deux choses passent au travers : la
réécriture suivie d'un `os.utime` délibéré, et l'altération du contenu *sous*
le système de fichiers (bitrot, câble défaillant, RAM sans ECC). La première
est un geste d'adversaire, et ce module n'en a jamais visé un : son MD5
lui-même « détecte une corruption, il n'authentifie rien » (`scan.hash_file`),
et qui peut réécrire un mod peut tout aussi bien réécrire `gamma-md5.txt`, qui
est un fichier texte du même utilisateur. La seconde est réelle, et c'est
exactement ce que `verify --full` existe pour couvrir.

La date est lue **avant** le hachage, jamais après, et c'est structurel : si le
fichier est modifié pendant qu'on le lit, la mtime enregistrée reste
l'ancienne, donc plus vieille que celle du disque — le passage suivant voit un
écart et rehache. Enregistrer la mtime d'après lecture ferait l'inverse : elle
collerait à un contenu qu'on a lu à cheval sur la modification, et le
court-circuit figerait cette empreinte incohérente pour toujours.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileStat:
    """Taille et date de dernière modification — ce qui se compare sans lire le contenu.

    En nanosecondes (`st_mtime_ns`) et non en `float` : `st_mtime` arrondit, et
    deux écritures dans la même milliseconde deviendraient indistinguables.
    """

    size: int
    mtime_ns: int

    @classmethod
    def of(cls, path: Path) -> FileStat:
        """`FileStat` de `path`. Lève `OSError` — l'appelant range ça dans les illisibles.

        Suit les liens symboliques, comme `hash_file` qui ouvre le fichier :
        les deux doivent parler du même contenu.
        """
        info = path.stat()
        return cls(size=info.st_size, mtime_ns=info.st_mtime_ns)


@dataclass(frozen=True, slots=True)
class KnownFile:
    """Ce que la référence sait d'un fichier : son empreinte, et de quoi savoir si elle vaut encore.

    N'existe que pour les entrées de référence qui portent la colonne
    taille/mtime. Une ancienne référence n'en produit aucune, et c'est le repli
    sûr : pas de `KnownFile`, pas de court-circuit, tout est rehaché.
    """

    digest: str
    stat: FileStat
