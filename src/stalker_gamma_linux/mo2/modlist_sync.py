"""Lecture/écriture de `modlist.txt` et de l'instantané amont qui rend la fusion possible.

`modlist_merge` est pur — il ne connaît que trois chaînes. Ce module-ci est la
seule couche qui touche au disque, et il porte les trois précautions qui vont
avec :

1. **Les fins de ligne d'origine sont préservées.** L'instance MO2 vient de
   Windows : sur l'install de test, `profiles/G.A.M.M.A/modlist.txt` est en
   CRLF. `Path.read_text` applique la traduction universelle des sauts de
   ligne et rendrait un texte en LF — le fichier réécrit changerait alors
   d'encodage de ligne d'un bout à l'autre, sans que personne l'ait demandé.
   D'où `open(..., newline="")` en lecture **et** en écriture.
2. **Jamais de mutation en place.** On écrit un fichier voisin puis on le
   met à la place par `os.replace` : une coupure de courant en plein milieu
   laisse l'ancien fichier intact, jamais un `modlist.txt` tronqué — qui
   ferait démarrer MO2 sans aucun mod.
3. **L'instantané amont est pris juste après le moteur**, jamais après que le
   joueur ait pu toucher la liste : c'est ce qui garantit que `base` est bien
   « ce que l'amont avait écrit la fois d'avant », et pas un mélange.

L'instantané vit sous `<root>/backups/` (voir `backups.paths`) : il protège la
même chose que les sauvegardes et doit suivre l'installation, pas la
configuration XDG de la machine qui l'a lancée.
"""

from __future__ import annotations

import os
from pathlib import Path

from stalker_gamma_linux.backups.paths import upstream_modlist_snapshot
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2.errors import ModlistSyncError
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.modlist_merge import MergeOutcome, merge_modlists
from stalker_gamma_linux.mo2.paths import Mo2Paths

MODLIST_FILENAME = "modlist.txt"
_TMP_SUFFIX = ".sgl-tmp"


def modlist_path(root: Path, *, profile: str = GAMMA_PROFILE) -> Path:
    return Mo2Paths.under(root).profile(profile) / MODLIST_FILENAME


def read_verbatim(path: Path) -> str | None:
    """Contenu de `path` **sans traduction des sauts de ligne**, ou `None` s'il n'existe pas.

    `errors="replace"` : un octet non-UTF-8 dans un nom de mod ne doit pas
    faire échouer une mise à jour. Le nom sera légèrement abîmé dans la copie,
    ce qui est infiniment préférable à une exception au milieu d'un update de
    plusieurs heures.
    """
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            return handle.read()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ModlistSyncError(path, error) from error


def write_atomic(path: Path, text: str) -> None:
    """Écrit `text` à côté puis remplace `path`. Jamais d'écriture en place."""
    temporary = path.with_name(path.name + _TMP_SUFFIX)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ModlistSyncError(path, error) from error


def read_snapshot(root: Path) -> str | None:
    """Dernière liste amont enregistrée, ou `None` s'il n'y en a pas encore."""
    return read_verbatim(upstream_modlist_snapshot(root))


def write_snapshot(root: Path, text: str) -> Path:
    """Enregistre `text` comme la liste amont de référence pour la prochaine fusion."""
    path = upstream_modlist_snapshot(root)
    write_atomic(path, text)
    return path


def record_upstream_snapshot(root: Path, *, profile: str = GAMMA_PROFILE) -> Path | None:
    """Prend l'instantané du `modlist.txt` courant comme liste amont de référence.

    À n'appeler qu'immédiatement après que le moteur a (ré)écrit le profil —
    c'est-à-dire à la fin de l'étape `gamma` d'une installation, ou après un
    `update`. Appelé à un autre moment, il enregistrerait la liste *du joueur*
    comme référence amont, et la fusion suivante ne verrait plus aucun de ses
    écarts.
    """
    text = read_verbatim(modlist_path(root, profile=profile))
    if text is None:
        return None
    return write_snapshot(root, text)


def merge_upstream_modlist(
    root: Path, previous_text: str | None, *, profile: str = GAMMA_PROFILE
) -> MergeOutcome:
    """Rejoue les écarts du joueur sur la liste amont fraîchement écrite.

    `previous_text` est le `modlist.txt` **lu avant** que le moteur ne tourne
    (c'est `ours`). Écrit le résultat et met à jour l'instantané amont dans
    tous les cas — y compris quand la fusion s'abstient, sinon la fusion
    suivante repartirait d'une référence périmée.

    Ne lève que `ModlistSyncError` (I/O). Une abstention n'est pas une erreur :
    elle sort dans `MergeOutcome.merged=False` avec son motif.
    """
    path = modlist_path(root, profile=profile)
    upstream_text = read_verbatim(path)
    if upstream_text is None:
        return MergeOutcome(
            merged=False,
            reason=_("no mod list at {path} after the update").format(path=path),
        )

    outcome = _merge(root, previous_text, upstream_text)
    if outcome.merged and outcome.text is not None and outcome.text != upstream_text:
        write_atomic(path, outcome.text)
    # L'instantané suit toujours l'amont, jamais le résultat fusionné : c'est
    # « ce que l'amont a écrit », pas « ce que le joueur a maintenant ».
    write_snapshot(root, upstream_text)
    return outcome


def _merge(root: Path, previous_text: str | None, upstream_text: str) -> MergeOutcome:
    if previous_text is None:
        return MergeOutcome(
            merged=False,
            reason=_("there was no mod list before the update — nothing to carry over"),
        )
    base_text = read_snapshot(root)
    if base_text is None:
        return MergeOutcome(
            merged=False,
            reason=_(
                "no upstream snapshot recorded yet — this update records one, and the "
                "next one will keep your mod list"
            ),
        )
    return merge_modlists(base_text, previous_text, upstream_text)
