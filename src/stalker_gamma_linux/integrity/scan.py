"""Parcours de `gamma/mods/` et calcul des empreintes MD5.

Cinq contraintes dictent la forme de ce module, et elles viennent toutes de
la taille réelle d'une install GAMMA (~83 Gio de mods, plusieurs centaines de
milliers de fichiers) :

1. **Lecture par blocs.** Certaines archives de mods dépassent le gigaoctet une
   fois extraites ; charger un fichier en mémoire pour le hacher ferait tomber
   la machine avant de rendre un verdict.
2. **Progression cadencée au temps écoulé**, jamais à l'index (`i % 500 == 0`).
   Les fichiers de mods sont très inégaux : quelques dizaines d'octets pour un
   `.ltx`, plusieurs gigaoctets pour une texture pack. Cadencer au nombre de
   fichiers donne une interface figée pendant de longues secondes dès qu'on
   tombe sur les gros, puis un déluge de lignes sur les petits. Le compteur est
   aussi rafraîchi **pendant** la lecture d'un même fichier, pour la même
   raison.
3. **Un fichier illisible n'arrête pas le scan.** Droits cassés, secteur mort,
   fichier ouvert par un autre processus : c'est précisément ce qu'on cherche à
   détecter. On le range dans `unreadable` et on continue.
4. **On ne relit que ce qui a pu changer.** Le scan le plus fréquent est
   celui où rien n'a bougé depuis la veille ; relire 83 Gio pour le
   redécouvrir est le vrai coût de la commande, pas le MD5. Quand la référence
   porte la taille et la date d'un fichier (`baseline`, `fingerprint`) et que
   le disque les donne identiques, l'empreinte est reprise de la référence
   sans ouvrir le fichier. `reference=None` — ce que passe `verify --full` —
   rétablit le scan intégral. Le compromis exact, et ce qu'il laisse passer,
   sont écrits dans `fingerprint`.
5. **Hachage parallèle, résultat séquentiel.** Un seul fil ne tient que
   ~430 Mio/s sur une arborescence réaliste, là où MD5 seul rend ~840 Mio/s
   par cœur : le reste part en ouvertures de fichiers et en attente disque.
   `hashlib` libérant le GIL, quelques fils en récupèrent une bonne part
   (chiffres mesurés dans `_default_workers`) — sans `multiprocessing`, dont
   le coût de sérialisation mangerait le gain. Le pool ne change **rien** à ce
   que voit l'appelant : les tâches sont consommées dans l'ordre de
   soumission, donc dans l'ordre de parcours (voir `scan_tree`).

L'annulation est vérifiée entre deux blocs, pas seulement entre deux fichiers :
un `cancel_event` levé au milieu d'un fichier de 4 Gio doit rendre la main tout
de suite. Elle **lève** `IntegrityCancelledError` au lieu de retourner un
résultat partiel — c'est la garantie structurelle qu'un scan interrompu ne peut
pas atteindre `write_baseline`.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from stalker_gamma_linux import output, sizing
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity import storage
from stalker_gamma_linux.integrity.errors import IntegrityCancelledError
from stalker_gamma_linux.integrity.fingerprint import FileStat, KnownFile

# 1 Mio : assez grand pour que le coût par appel disparaisse, assez petit pour
# que l'annulation et la progression restent réactives sur un gros fichier.
BLOCK_SIZE = 1024 * 1024

# Cadence des lignes de progression. Assez espacé pour ne pas noyer la console
# sur des milliers de petits fichiers, assez court pour qu'une interface ne
# paraisse jamais figée.
PROGRESS_INTERVAL_SECONDS = 1.5

# Plafond de fils de hachage sur un support non mécanique (voir
# `_default_workers` pour le pourquoi de ce chiffre-là).
MAX_HASH_WORKERS = 4

# Fichiers en vol par fil. Les tâches sont soumises par fenêtre glissante et
# non toutes d'un coup : sur 300 000 fichiers, tout empiler immobiliserait des
# centaines de Mio rien qu'en objets `Future`. Assez profond, tout de même,
# pour qu'un gros fichier en tête de file ne laisse pas les autres fils
# inoccupés le temps qu'il se termine.
QUEUE_DEPTH_PER_WORKER = 8

Clock = Callable[[], float]


class CancelSignal(Protocol):
    """Tout ce que le hachage demande à un signal d'annulation : savoir s'il est levé.

    `threading.Event` satisfait ce contrat tel quel — l'élargissement n'existe
    que pour pouvoir passer aux fils la *combinaison* de l'annulation demandée
    par l'appelant et de l'arrêt interne du pool (voir `_AnySignal`).
    """

    def is_set(self) -> bool: ...


class _AnySignal:
    """Signal levé dès que l'un de ceux qu'il agrège l'est."""

    __slots__ = ("_signals",)

    def __init__(self, *signals: CancelSignal | None) -> None:
        self._signals = tuple(signal for signal in signals if signal is not None)

    def is_set(self) -> bool:
        return any(signal.is_set() for signal in self._signals)


@dataclass(frozen=True, slots=True)
class UnreadableFile:
    """Un fichier (ou un dossier) que le scan n'a pas pu lire, et pourquoi."""

    relative: str
    reason: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Empreintes relevées, plus ce qui n'a pas pu être lu.

    `stats` couvre **tous** les fichiers de `digests`, court-circuités compris :
    c'est ce qui permet à la référence suivante de porter la colonne
    taille/mtime même pour des fichiers qu'on n'a pas relus. `reused` liste
    ceux-là, parce qu'un scan qui n'a rien relu et un scan qui a tout relu ne
    disent pas la même chose et que l'utilisateur doit voir lequel il a eu.
    """

    digests: Mapping[str, str]
    unreadable: tuple[UnreadableFile, ...] = ()
    total_bytes: int = 0
    stats: Mapping[str, FileStat] = field(default_factory=dict)
    reused: tuple[str, ...] = ()

    @property
    def file_count(self) -> int:
        return len(self.digests)

    @property
    def reused_count(self) -> int:
        return len(self.reused)


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    """Ce qu'un fil rend pour un fichier : son empreinte, son état disque, et s'il a été relu."""

    digest: str
    stat: FileStat
    reused: bool


class _ScanProgress:
    """Compteurs du scan + cadencement des rapports au temps écoulé.

    Petit objet à état volontairement isolé ici : c'est le seul endroit du
    module qui mute quoi que ce soit, et le reste (`ScanResult`,
    `UnreadableFile`) reste immuable.

    **Thread-safe.** `add_bytes` est appelée une fois par bloc et par fil de
    hachage. La course qui se voit vraiment est le « check-then-act » de la
    cadence : deux fils lisent la même heure, franchissent ensemble le test des
    1,5 s et s'écrasent mutuellement `_last_report` — les lignes de progression
    se doublent, et leur nombre varie d'une exécution à l'autre. Les `+=` des
    compteurs, eux, ne survivent aujourd'hui à l'absence de verrou que par
    accident : CPython ne préempte un fil qu'aux sauts et aux appels, jamais
    entre le chargement et le rangement d'un attribut. C'est un détail
    d'implémentation, pas une garantie du langage, et il tombe sur un
    interpréteur sans GIL. Le verrou couvre donc les deux.

    L'horloge est lue sous le verrou elle aussi : c'est ce qui permet aux tests
    d'injecter une horloge factice sans avoir à la rendre thread-safe. Le
    `reporter`, en revanche, est appelé **hors** verrou — une implémentation
    lente (rendu GTK, console) n'a pas à bloquer les fils qui hachent, et le
    cadencement à 1,5 s fait qu'un seul fil à la fois franchit le test, donc que
    les lignes sortent dans l'ordre.
    """

    def __init__(
        self,
        reporter: output.Reporter,
        *,
        clock: Clock,
        interval: float = PROGRESS_INTERVAL_SECONDS,
    ) -> None:
        self._reporter = reporter
        self._clock = clock
        self._interval = interval
        self._lock = threading.Lock()
        self._last_report = clock()
        self._files = 0
        self._total_bytes = 0

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    @property
    def files(self) -> int:
        with self._lock:
            return self._files

    def add_bytes(self, count: int) -> None:
        with self._lock:
            self._total_bytes += count
            due = self._due_snapshot()
        self._report(due)

    def add_file(self) -> None:
        with self._lock:
            self._files += 1
            due = self._due_snapshot()
        self._report(due)

    def _due_snapshot(self) -> tuple[int, int] | None:
        """Compteurs à publier si la cadence le permet, `None` sinon. Verrou tenu."""
        now = self._clock()
        if now - self._last_report < self._interval:
            return None
        self._last_report = now
        return self._files, self._total_bytes

    def _report(self, due: tuple[int, int] | None) -> None:
        if due is None:
            return
        files, total_bytes = due
        self._reporter.progress(
            _("  {files} files checked, {size} GiB read…").format(
                files=files, size=f"{total_bytes / sizing.GIB:.1f}"
            )
        )


def _raise_if_cancelled(cancel_event: CancelSignal | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise IntegrityCancelledError


def hash_file(
    path: Path,
    *,
    cancel_event: CancelSignal | None = None,
    on_block: Callable[[int], None] | None = None,
) -> tuple[str, int]:
    """`(md5 hexadécimal, taille lue)` de `path`, lu par blocs de `BLOCK_SIZE`.

    `usedforsecurity=False` : ce MD5 détecte une corruption, il n'authentifie
    rien. C'est aussi ce qui permet au scan de tourner sur une machine en mode
    FIPS, où `hashlib.md5()` sans ce drapeau refuse de s'initialiser. L'algo
    lui-même n'est pas un choix : c'est celui du modpack amont et des sommes
    que gamma-launcher vérifie déjà (`check-md5`).
    """
    digest = hashlib.md5(usedforsecurity=False)
    read_bytes = 0
    with path.open("rb") as handle:
        while True:
            _raise_if_cancelled(cancel_event)
            block = handle.read(BLOCK_SIZE)
            if not block:
                break
            digest.update(block)
            read_bytes += len(block)
            if on_block is not None:
                on_block(len(block))
    return digest.hexdigest(), read_bytes


def _walk_files(root: Path, on_error: Callable[[OSError], None]) -> Iterator[tuple[Path, str]]:
    """Chemins des fichiers sous `root`, avec leur chemin relatif POSIX.

    Ordre déterministe (tri en place de `dirnames`/`filenames`, ce que l'API
    `os.walk` attend explicitement) : deux scans de la même arborescence
    produisent la même progression, ce qui rend un rapport reproductible.
    `followlinks=False` (défaut) : un lien symbolique vers un dossier n'est
    jamais suivi — sinon un lien pointant vers la racine boucle à l'infini.
    `on_error` est branché parce que `os.walk` ignore **silencieusement** un
    dossier illisible par défaut : ici c'est exactement ce qu'on doit rapporter.
    """
    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        dirnames.sort()
        filenames.sort()
        current = Path(dirpath)
        for name in filenames:
            path = current / name
            yield path, path.relative_to(root).as_posix()


def _default_workers(root: Path) -> int:
    """Nombre de fils de hachage à lancer par défaut pour l'arborescence `root`.

    Deux régimes, parce que le parallélisme ne produit pas le même effet des
    deux côtés du miroir :

    - **Disque mécanique : un seul fil.** Quatre lecteurs concurrents sur
      quatre fichiers éloignés remplacent une lecture séquentielle à ~150 Mio/s
      par un va-et-vient de têtes ; le scan y perdrait au lieu d'y gagner. On
      retombe alors exactement sur le comportement d'avant le pool.
    - **Le reste : `MAX_HASH_WORKERS`, plafonné au nombre de cœurs.** Quatre,
      parce que c'est le coude de la courbe — pas parce que le chiffre est
      joli. Mesuré sur 7,86 Gio et 20 735 fichiers (NVMe, Ryzen 7 5700X3D,
      cache de pages vidé avant chaque passe) : 18,6 s à un fil, 12,5 s à
      deux, 10,4 s à quatre, 9,6 s à huit, 8,8 s à seize. Chaque doublement
      au-delà de quatre ne rend plus que ~8 %, parce que ce n'est plus MD5 qui
      borne — seul, il tient 3,2 Gio/s à quatre fils — mais la part de la
      boucle qui **garde** le GIL : ouvrir vingt mille fichiers et recopier
      leurs blocs. Payer quatre cœurs de plus pour 8 % n'a pas de sens sur une
      machine où le joueur fait autre chose pendant que le scan tourne.

    Un support indéterminable (`None` : btrfs multi-disques, NFS, conteneur
    sans `/proc`) est traité comme non mécanique. Le cas coûteux est celui des
    plateaux, et c'est justement celui qu'on sait reconnaître ; le doute, lui,
    porte surtout sur des supports modernes. Qui veut trancher autrement passe
    `workers=` à `scan_tree`.
    """
    if storage.is_rotational(root):
        return 1
    return min(MAX_HASH_WORKERS, os.cpu_count() or 1)


def _resolve_workers(workers: int | None, root: Path) -> int:
    if workers is None:
        return _default_workers(root)
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers!r}")
    return workers


def _unreadable_order(entry: UnreadableFile) -> tuple[str, str]:
    return entry.relative, entry.reason


def scan_tree(
    root: Path,
    *,
    reference: Mapping[str, KnownFile] | None = None,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
    clock: Clock = time.monotonic,
    workers: int | None = None,
) -> ScanResult:
    """Hache les fichiers sous `root`. Lève `IntegrityCancelledError` si annulé.

    `reference` : ce que la référence sait déjà de ces fichiers. Un fichier dont
    la taille **et** la date de modification correspondent n'est pas relu — son
    empreinte est reprise telle quelle et son chemin apparaît dans
    `reused`. `None` (défaut) rehache tout, et c'est ce que passe
    `verify --full` ; une référence à l'ancien format n'a aucune entrée, donc
    produit le même effet. Ce que ce court-circuit laisse passer est écrit dans
    `fingerprint`.

    `workers` : nombre de fils de hachage. `None` (défaut) le déduit du support
    qui porte `root` (`_default_workers`) ; `1` restaure un scan strictement
    séquentiel. **Le résultat n'en dépend pas** : mêmes empreintes, même ordre,
    quel que soit le nombre de fils. C'est l'ordre de *soumission* qui est
    consommé, jamais l'ordre d'achèvement — `digests` reste dans l'ordre de
    parcours, et `unreadable` est retrié en sortie puisque ses entrées naissent
    des deux côtés (parcours et hachage) et donc à des moments décalés.

    Une implémentation de `reporter` doit désormais tolérer d'être appelée
    depuis un fil de hachage. Les deux du projet le font (`console_reporter`
    s'appuie sur le verrou de `rich`, `gui.worker.QueueReporter` sur une
    `queue.Queue`).
    """
    worker_count = _resolve_workers(workers, root)
    known: Mapping[str, KnownFile] = reference if reference is not None else {}
    digests: dict[str, str] = {}
    stats: dict[str, FileStat] = {}
    reused: list[str] = []
    unreadable: list[UnreadableFile] = []
    progress = _ScanProgress(reporter, clock=clock)

    def on_walk_error(error: OSError) -> None:
        name = error.filename if isinstance(error.filename, str) else str(root)
        unreadable.append(UnreadableFile(relative=_relative_to(root, name), reason=str(error)))

    # `abort` double le `cancel_event` de l'appelant, qui peut être absent :
    # toute sortie de la boucle — annulation, Ctrl-C, erreur inattendue — doit
    # stopper les fils en vol au bloc suivant. Sans lui, le `shutdown` du
    # `finally` attendrait la fin d'un fichier de plusieurs Gio avant de rendre
    # la main, et un Ctrl-C paraîtrait ignoré.
    abort = threading.Event()
    stop_signal = _AnySignal(cancel_event, abort)

    def fingerprint_one(path: Path, relative: str) -> _Fingerprint:
        """Empreinte d'un fichier — reprise de la référence s'il n'a pas bougé.

        Le `stat` est pris **avant** le hachage, et c'est structurel : une
        modification survenue pendant la lecture donnera au fichier une date
        plus récente que celle qu'on enregistre, donc un écart au passage
        suivant. L'ordre inverse figerait une empreinte lue à cheval sur cette
        modification en la déclarant à jour (voir `fingerprint`).

        Le `stat` est fait ici, dans le fil de hachage, et non pendant le
        parcours : sur 300 000 fichiers, ces appels système représentent
        justement l'essentiel du travail restant quand plus rien n'est relu.
        """
        stat = FileStat.of(path)
        entry = known.get(relative)
        if entry is not None and entry.stat == stat:
            return _Fingerprint(digest=entry.digest, stat=stat, reused=True)
        digest, _size = hash_file(path, cancel_event=stop_signal, on_block=progress.add_bytes)
        return _Fingerprint(digest=digest, stat=stat, reused=False)

    def collect(relative: str, task: Future[_Fingerprint]) -> None:
        """Range le résultat d'un fichier — appelée dans l'ordre de soumission."""
        try:
            outcome = task.result()
        except OSError as error:
            unreadable.append(UnreadableFile(relative=relative, reason=str(error)))
            return
        digests[relative] = outcome.digest
        stats[relative] = outcome.stat
        if outcome.reused:
            reused.append(relative)
        progress.add_file()

    executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="gamma-md5")
    pending: deque[tuple[str, Future[_Fingerprint]]] = deque()
    window = worker_count * QUEUE_DEPTH_PER_WORKER
    try:
        for path, relative in _walk_files(root, on_walk_error):
            _raise_if_cancelled(cancel_event)
            pending.append((relative, executor.submit(fingerprint_one, path, relative)))
            if len(pending) >= window:
                collect(*pending.popleft())
        while pending:
            _raise_if_cancelled(cancel_event)
            collect(*pending.popleft())
    finally:
        # `cancel_futures` jette ce qui n'a pas démarré, `abort` fait sortir les
        # fils actifs au bloc suivant (~1 Mio), et `wait=True` les attend : au
        # retour de `scan_tree`, plus aucun fil de hachage ne survit.
        abort.set()
        executor.shutdown(wait=True, cancel_futures=True)

    return ScanResult(
        digests=digests,
        unreadable=tuple(sorted(unreadable, key=_unreadable_order)),
        total_bytes=progress.total_bytes,
        stats=stats,
        reused=tuple(reused),
    )


def _relative_to(root: Path, raw: str) -> str:
    """Chemin relatif à `root` quand c'est possible, sinon le chemin tel quel."""
    try:
        return Path(raw).relative_to(root).as_posix()
    except ValueError:
        return raw
