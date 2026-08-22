"""Parcours de `gamma/mods/` et calcul des empreintes MD5, fichier par fichier.

Trois contraintes dictent la forme de ce module, et elles viennent toutes de la
taille réelle d'une install GAMMA (~83 Gio de mods, plusieurs centaines de
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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux import output, sizing
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity.errors import IntegrityCancelledError

# 1 Mio : assez grand pour que le coût par appel disparaisse, assez petit pour
# que l'annulation et la progression restent réactives sur un gros fichier.
BLOCK_SIZE = 1024 * 1024

# Cadence des lignes de progression. Assez espacé pour ne pas noyer la console
# sur des milliers de petits fichiers, assez court pour qu'une interface ne
# paraisse jamais figée.
PROGRESS_INTERVAL_SECONDS = 1.5

Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class UnreadableFile:
    """Un fichier (ou un dossier) que le scan n'a pas pu lire, et pourquoi."""

    relative: str
    reason: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Empreintes relevées, plus ce qui n'a pas pu être lu."""

    digests: Mapping[str, str]
    unreadable: tuple[UnreadableFile, ...] = ()
    total_bytes: int = 0

    @property
    def file_count(self) -> int:
        return len(self.digests)


class _ScanProgress:
    """Compteurs du scan + cadencement des rapports au temps écoulé.

    Petit objet à état volontairement isolé ici : c'est le seul endroit du
    module qui mute quoi que ce soit, et le reste (`ScanResult`,
    `UnreadableFile`) reste immuable.
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
        self._last_report = clock()
        self.files = 0
        self.total_bytes = 0

    def add_bytes(self, count: int) -> None:
        self.total_bytes += count
        self._report_if_due()

    def add_file(self) -> None:
        self.files += 1
        self._report_if_due()

    def _report_if_due(self) -> None:
        now = self._clock()
        if now - self._last_report < self._interval:
            return
        self._last_report = now
        self._reporter.progress(
            _("  {files} files checked, {size} GiB read…").format(
                files=self.files, size=f"{self.total_bytes / sizing.GIB:.1f}"
            )
        )


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise IntegrityCancelledError


def hash_file(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
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


def scan_tree(
    root: Path,
    *,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
    clock: Clock = time.monotonic,
) -> ScanResult:
    """Hache tous les fichiers sous `root`. Lève `IntegrityCancelledError` si annulé."""
    digests: dict[str, str] = {}
    unreadable: list[UnreadableFile] = []
    progress = _ScanProgress(reporter, clock=clock)

    def on_walk_error(error: OSError) -> None:
        name = error.filename if isinstance(error.filename, str) else str(root)
        unreadable.append(UnreadableFile(relative=_relative_to(root, name), reason=str(error)))

    for path, relative in _walk_files(root, on_walk_error):
        _raise_if_cancelled(cancel_event)
        try:
            digest, _size = hash_file(path, cancel_event=cancel_event, on_block=progress.add_bytes)
        except OSError as error:
            unreadable.append(UnreadableFile(relative=relative, reason=str(error)))
            continue
        digests[relative] = digest
        progress.add_file()

    return ScanResult(
        digests=digests, unreadable=tuple(unreadable), total_bytes=progress.total_bytes
    )


def _relative_to(root: Path, raw: str) -> str:
    """Chemin relatif à `root` quand c'est possible, sinon le chemin tel quel."""
    try:
        return Path(raw).relative_to(root).as_posix()
    except ValueError:
        return raw
