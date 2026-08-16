"""Fusion Anomaly + mods pour le mode flat, par **liens durs**.

Pourquoi ne pas déléguer à `gamma-launcher usvfs-workaround` comme partout
ailleurs : parce qu'il fait des `copytree`. Mesuré dans son code (v3.1,
`commands/usvfs.py`) — Anomaly puis chaque mod sont *copiés* dans le dossier
final. Le mode flat coûtait donc une seconde installation complète, soit
~100 Gio pour un simple fallback. Un lien dur donne exactement le même arbre
pour le prix de quelques inodes.

C'est notre seule divergence assumée vis-à-vis du moteur amont, et elle est
justifiée par la mesure. Le correctif a vocation à remonter chez lui (option
`--link`) : ce module réimplémente une fusion, pas la résolution ModDB ni le
parsing des directives d'extraction — la logique qui fait la valeur de
gamma-launcher reste chez gamma-launcher.

**Ordre d'application.** `modlist.txt` de MO2 est écrit par priorité
croissante de bas en haut : on applique donc de bas en haut (`reversed`), si
bien qu'un mod plus prioritaire écrase ceux d'en dessous. Identique à l'amont.
Le `bin/` d'Anomaly est réappliqué en dernier, également comme l'amont.

**Le piège des liens durs**, et ce qu'on en fait : deux noms partagent le même
inode, donc modifier un fichier de l'arbre fusionné modifierait aussi le
fichier du mod d'origine. C'est acceptable pour des données que le jeu ne fait
que lire, mais pas pour ce qu'il réécrit — d'où `_COPIED_SUBTREES` : tout ce
qui vit sous `appdata/` (réglages, sauvegardes, cache de shaders) est **copié**,
jamais lié. Quelques Mio, et l'installation MO2 d'origine reste intouchable.
"""

from __future__ import annotations

import errno
import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2.errors import Mo2CancelledError, Mo2InstanceError
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.modlist import enabled_mods, read_modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths

ProgressCallback = Callable[[str], None]

# Sous-arbres du dossier fusionné que le jeu réécrit : copiés, jamais liés.
_COPIED_SUBTREES: tuple[str, ...] = ("appdata",)

# Fréquence de vérification de l'annulation (en fichiers) : assez fin pour que
# la GUI réponde, assez large pour ne pas payer un `Event.is_set()` par fichier
# sur les ~200 000 fichiers d'une install GAMMA.
_CANCEL_CHECK_EVERY = 512


@dataclass(frozen=True, slots=True)
class MergeReport:
    """Ce que la fusion a réellement fait — affiché à l'utilisateur."""

    mods: int
    linked: int
    copied: int
    shared_bytes: int
    missing: tuple[str, ...]

    @property
    def summary(self) -> str:
        gib = self.shared_bytes / 1024**3
        return _(
            "Merged {mods} mods: {linked} files hardlinked ({gib:.1f} GiB shared "
            "instead of duplicated), {copied} copied."
        ).format(mods=self.mods, linked=self.linked, gib=gib, copied=self.copied)


def _is_copied(relative: Path) -> bool:
    parts = relative.parts
    return bool(parts) and parts[0].lower() in _COPIED_SUBTREES


def _place(source: Path, destination: Path) -> tuple[bool, int]:
    """Pose `source` en `destination` (lien dur, sinon copie). Retourne (lié, octets)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        # Un mod plus prioritaire écrase celui d'en dessous : on retire le lien
        # existant plutôt que d'écrire dedans — écrire suivrait l'inode et
        # modifierait le fichier du mod précédent.
        destination.unlink()
    size = source.stat().st_size
    try:
        os.link(source, destination)
    except OSError as error:
        # EXDEV : dossier final sur un autre système de fichiers. EPERM/EMLINK :
        # système de fichiers sans liens durs. Dans tous ces cas la copie reste
        # correcte, seulement plus coûteuse — on ne fait pas échouer la fusion.
        if error.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK):
            raise
        shutil.copy2(source, destination)
        return False, size
    return True, size


def _merge_tree(
    source: Path,
    destination: Path,
    counters: dict[str, int],
    cancel_event: threading.Event | None,
) -> None:
    """Fusionne récursivement `source` dans `destination`, fichier à fichier."""
    for root, _dirs, files in os.walk(source):
        root_path = Path(root)
        for name in files:
            relative = (root_path / name).relative_to(source)
            target = destination / relative
            if _is_copied(relative):
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                shutil.copy2(root_path / name, target)
                counters["copied"] += 1
            else:
                linked, size = _place(root_path / name, target)
                counters["linked" if linked else "copied"] += 1
                if linked:
                    counters["shared_bytes"] += size
            counters["seen"] += 1
            if (
                cancel_event is not None
                and counters["seen"] % _CANCEL_CHECK_EVERY == 0
                and cancel_event.is_set()
            ):
                raise Mo2CancelledError(_("Merge cancelled."))


def build_merged_install(
    anomaly: Path,
    mo2: Mo2Paths,
    final_dir: Path,
    *,
    profile: str = GAMMA_PROFILE,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> MergeReport:
    """Construit l'installation fusionnée dans `final_dir`. Retourne ce qui a été fait.

    Lève `Mo2InstanceError` si Anomaly ou le profil sont introuvables,
    `Mo2CancelledError` si `cancel_event` est levé en cours de route (le dossier
    partiel est laissé en place : la fusion est idempotente, une relance le
    complète).
    """
    progress = on_progress or (lambda _line: None)
    if not anomaly.is_dir():
        raise Mo2InstanceError(
            _("Anomaly folder not found: {path}").format(path=anomaly),
        )
    mods = enabled_mods(read_modlist(mo2.profile(profile)))
    if not mods:
        raise Mo2InstanceError(
            _(
                "No enabled mod found in profile « {profile} » ({path}).\n"
                "Install the modpack first — a flat merge of Anomaly alone would "
                "just be vanilla Anomaly."
            ).format(profile=profile, path=mo2.profile(profile))
        )

    final_dir.mkdir(parents=True, exist_ok=True)
    counters = {"linked": 0, "copied": 0, "shared_bytes": 0, "seen": 0}

    progress(_("Merging Anomaly…"))
    _merge_tree(anomaly, final_dir, counters, cancel_event)

    missing: list[str] = []
    total = len(mods)
    # De bas en haut : le plus prioritaire est appliqué en dernier, donc gagne.
    for index, mod in enumerate(reversed(mods), start=1):
        source = mo2.mods / mod
        if not source.is_dir():
            missing.append(mod)
            continue
        progress(_("Merging mod {index}/{total}: {mod}").format(index=index, total=total, mod=mod))
        _merge_tree(source, final_dir, counters, cancel_event)

    # Les binaires d'Anomaly repassent en dernier : un mod peut avoir déposé
    # des fichiers dans `bin/`, mais l'exécutable qui doit tourner est celui du
    # jeu de base (même règle que gamma-launcher).
    progress(_("Restoring Anomaly binaries…"))
    _merge_tree(anomaly / "bin", final_dir / "bin", counters, cancel_event)

    if missing:
        progress(
            _("Warning: {count} enabled mods have no folder and were skipped: {mods}").format(
                count=len(missing), mods=", ".join(missing[:5])
            )
        )
    report = MergeReport(
        mods=total - len(missing),
        linked=counters["linked"],
        copied=counters["copied"],
        shared_bytes=counters["shared_bytes"],
        missing=tuple(missing),
    )
    progress(report.summary)
    return report
