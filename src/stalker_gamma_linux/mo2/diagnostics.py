"""Diagnostics post-lancement : runtime/préfixe en amont, puis USVFS mort.

Deux familles de diagnostics, dans l'ordre où les échecs surviennent réellement :

0. **En amont de l'USVFS** : le processus cible ne démarre même pas.
   `launch_failure_diagnosis`/`diagnose_launch_log` reconnaissent, sur le
   journal de lancement umu-run, un runtime VC++ manquant
   (concrt140/msvcp140/vcruntime140) ou un préfixe construit par une autre
   version de Proton (wineserver refuse de démarrer). Ces échecs masquent tout
   diagnostic USVFS ultérieur : ce message s'affiche **à la place** du message
   USVFS générique, jamais en plus.

   Le journal en question est celui d'un lancement de *jeu*
   (`prefix.process.run_detached`, `logs/mo2-game.log` ou `flat-game.log`),
   ouvert en **append** : seule sa dernière session est diagnostiquée, sinon
   l'échec d'une partie précédente ressortirait comme s'il venait d'arriver.
   Depuis T15, plus personne ne lit ces fonctions au retour de `play` (le jeu
   tourne encore) : c'est le paquet `postmortem` qui les rappelle après coup.

Le symptôme n°1 du mode MO2 sous Proton est un jeu qui se lance **sans contenu
GAMMA** parce que le VFS n'a pas été monté (version de Proton incompatible, ou
jeu lancé hors MO2). On le détecte sur des signaux réels, inspectables côté
Linux :

1. Le dernier `logs/usvfs-*.log` de l'instance montre-t-il que le VFS a été
   injecté dans le processus du jeu et sert des fichiers ? Marqueurs relevés sur
   un vrai run modé qui fonctionne (usvfs 0.5.6.1, GE-Proton11-1, Wine 10) :
   `inithooks in process <pid> successful` (hooks posés dans un process cible) et
   `mapping file in vfs:` (le VFS sert effectivement des fichiers au jeu).
2. Le profil `G.A.M.M.A` a-t-il bien des mods activés (`modlist.txt`) ? Sinon,
   MO2 n'a rien à monter — c'est un problème de configuration, pas d'USVFS.

Le diagnostic est **indicatif** : les logs usvfs varient selon les versions, donc
`play` réussit toujours si le jeu s'est lancé — on affiche seulement un
avertissement si les marqueurs de VFS vivant manquent. Les remèdes renvoient vers
`docs/MO2-PROTON-COMPAT.md`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.modlist import enabled_mods, read_modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix.paths import PrefixPaths

_USVFS_LOG_GLOB = "usvfs-*.log"

# Journaux de lancement écrits par `prefix.process.run_detached` : un fichier
# fixe par mode de lancement, ouvert en **append** à chaque partie.
LAUNCH_LOG_NAMES = ("mo2-game.log", "flat-game.log")

# Ligne que `run_detached` écrit en tête de chaque lancement (`$ <commande>`) :
# c'est le seul séparateur de sessions dans un journal append-only.
_LAUNCH_SESSION_RE = re.compile(r"^\$ .*$", re.MULTILINE)

# Signaux d'un VFS vivant, tirés d'un vrai log usvfs qui fonctionne : les hooks
# ont été posés dans un process cible (le jeu), et/ou des fichiers sont
# effectivement servis par le VFS. Le marqueur historique « proxy run successful »
# des forums ne correspond PAS à usvfs 0.5.6.1 (faux négatif constaté en réel).
_INITHOOKS_OK_RE = re.compile(r"inithooks in process \d+ successful")
_VFS_MAPPING_MARKER = "mapping file in vfs:"

_COMPAT_DOC = "docs/MO2-PROTON-COMPAT.md"

# Ces deux échecs surviennent EN AMONT de l'USVFS (le process cible ne démarre
# même pas) : les marqueurs viennent du journal de lancement umu-run capturé
# par `prefix.process.run_in_prefix` (fichier `mo2-game-*.log`), pas du journal
# usvfs. Recherche insensible à la casse : voir `launch_failure_diagnosis`.
_VCRUNTIME_DLL_MARKERS = ("concrt140.dll", "msvcp140.dll", "vcruntime140.dll")
_PREFIX_VERSION_MARKERS = (
    "version mismatch",
    "wrong wineserver",
    "prefix has an invalid version",
    "wine binary was not upgraded correctly",
)


def _vcruntime_missing_message() -> str:
    return _(
        "⚠ Missing VC++ runtime in the shared prefix (concrt140.dll / "
        "msvcp140.dll / vcruntime140.dll not found): this fails before USVFS "
        "even gets a chance to mount.\n"
        "→ `stalker-gamma-linux prefix-doctor --repair` (reinstalls the "
        "missing verbs). See {doc}."
    ).format(doc=_COMPAT_DOC)


def _prefix_version_mismatch_message() -> str:
    return _(
        "⚠ This prefix was built by a different Proton/Wine build than the one "
        "currently configured: wineserver refuses to run against it (version "
        "mismatch) — this fails before USVFS even gets a chance to mount.\n"
        "→ `stalker-gamma-linux install --only prefix` (rebuilds the shared "
        "prefix from scratch with the configured Proton build). See {doc}."
    ).format(doc=_COMPAT_DOC)


# Ordre = ordre de vérification ; le premier marqueur trouvé gagne (un seul
# diagnostic principal à la fois, cf. `launch_failure_diagnosis`).
_LAUNCH_FAILURE_RULES: tuple[tuple[tuple[str, ...], Callable[[], str]], ...] = (
    (_VCRUNTIME_DLL_MARKERS, _vcruntime_missing_message),
    (_PREFIX_VERSION_MARKERS, _prefix_version_mismatch_message),
)


def launch_failure_diagnosis(log_text: str) -> str | None:
    """Diagnostic amont (runtime VC++ manquant / préfixe incompatible) sur le
    journal de lancement umu-run (recherche insensible à la casse).

    Retourne le message de remède si un échec connu est reconnu, sinon None.
    Ces échecs se produisent avant que l'USVFS ait la moindre chance de
    monter : l'appelant (`session.run_play`) doit afficher ce message **à la
    place** du diagnostic USVFS générique, jamais en plus.
    """
    lowered = log_text.lower()
    for markers, build_message in _LAUNCH_FAILURE_RULES:
        if any(marker in lowered for marker in markers):
            return build_message()
    return None


def latest_launch_log(prefix: PrefixPaths) -> Path | None:
    """Journal de lancement du jeu le plus récent (mode MO2 ou mode flat).

    Les deux modes écrivent chacun dans un fichier au nom fixe ; c'est donc la
    date de modification, et non le nom, qui dit lequel décrit la dernière
    partie.
    """
    existing = [
        candidate for name in LAUNCH_LOG_NAMES if (candidate := prefix.logs / name).is_file()
    ]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def last_launch_session(log_text: str) -> str:
    """Dernier bloc `$ <commande>` du journal — la partie qui vient de tourner.

    `run_detached` ouvre son journal en **append** : un fichier réel en contient
    plusieurs (trois, sur l'install de test). Diagnostiquer le fichier entier
    ferait ressortir l'échec d'une partie d'il y a trois semaines comme s'il
    venait d'arriver — un faux positif garanti dès la deuxième partie.
    """
    starts = [match.start() for match in _LAUNCH_SESSION_RE.finditer(log_text)]
    return log_text[starts[-1] :] if starts else log_text


def read_launch_log(log_path: Path) -> str | None:
    """Contenu du journal de lancement, décodage **tolérant**.

    `system.read_text` décode en UTF-8 strict et rend None au premier octet
    invalide. Or `run_detached` redirige la sortie du processus *directement*
    dans ce fichier — sans le `errors="replace"` que `run_in_prefix` applique à
    son flux — et Wine émet des octets non-UTF-8 (0x88 constaté). Un journal
    ainsi pollué n'aurait produit aucun diagnostic du tout, silencieusement.
    """
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def diagnose_launch_log(log_path: Path | None) -> str | None:
    """Cherche un échec runtime/préfixe connu dans la **dernière** session du
    journal de lancement. None si le chemin est absent ou illisible — pas de
    faux diagnostic sur un journal introuvable."""
    if log_path is None:
        return None
    text = read_launch_log(log_path)
    if text is None:
        return None
    return launch_failure_diagnosis(last_launch_session(text))


@dataclass(frozen=True, slots=True)
class UsvfsDiagnosis:
    """Verdict du diagnostic post-lancement."""

    active: bool
    checked_log: Path | None
    enabled_mod_count: int
    message: str


def latest_usvfs_log(mo2: Mo2Paths) -> Path | None:
    """Journal USVFS le plus récent de l'instance, ou None s'il n'y en a aucun.

    Le nom horodaté (`usvfs-AAAA-MM-JJ_HH-MM-SS.log`, zéro-padé) rend l'ordre
    lexicographique équivalent à l'ordre chronologique.
    """
    logs_dir = mo2.logs
    if not logs_dir.is_dir():
        return None
    candidates = sorted(logs_dir.glob(_USVFS_LOG_GLOB))
    return candidates[-1] if candidates else None


def usvfs_active_in(log_text: str) -> bool:
    """Vrai si le journal indique un VFS vivant : hooks posés dans un process
    cible (`inithooks in process N successful`) ou fichiers servis par le VFS
    (`mapping file in vfs:`)."""
    return bool(_INITHOOKS_OK_RE.search(log_text)) or _VFS_MAPPING_MARKER in log_text


def _no_log_message(enabled: int) -> str:
    return _(
        "No USVFS log ({glob}) found: can't confirm the VFS mounted.\n"
        "→ Launch the game **via MO2** (the `play` command, not the executable "
        "directly) at least once. G.A.M.M.A profile: {enabled} mods enabled."
    ).format(glob=_USVFS_LOG_GLOB, enabled=enabled)


def _dead_no_mods_message() -> str:
    return _(
        "⚠ No mod enabled in the G.A.M.M.A profile (modlist.txt): MO2 has nothing to "
        "mount, the game will necessarily start vanilla.\n"
        "→ Reconfigure the instance (gamePath + profile), then check that the "
        "modpack install is complete (full-install / check-md5)."
    )


def _dead_message(log: Path, enabled: int) -> str:
    return _(
        "⚠ USVFS may be inactive: no live-VFS marker (target process hooks / "
        "mappings) found in {log}.\n"
        "If the game does show GAMMA content, ignore this warning (usvfs logs "
        "vary across versions). Otherwise, the game may have started vanilla "
        "despite {enabled} enabled mods — remedies (see {doc}):\n"
        "  1. Make sure you're launching via MO2 (moshortcut), not the exe directly.\n"
        "  2. Switch to Steam's *vanilla* Proton 9.0 or 10.0 (most reliable).\n"
        "  3. Try GE-Proton9-20.\n"
        "  4. Last resort: flat mode without MO2 (`play --flat`), at the cost of "
        "mod flexibility."
    ).format(log=log, enabled=enabled, doc=_COMPAT_DOC)


def _active_message(log: Path, enabled: int) -> str:
    return _(
        "USVFS active: the VFS was injected into the game and serves the mods "
        "({enabled} mods enabled in the G.A.M.M.A profile)."
    ).format(enabled=enabled)


def diagnose_usvfs(mo2: Mo2Paths, *, profile: str = GAMMA_PROFILE) -> UsvfsDiagnosis:
    """Diagnostique l'état de l'USVFS après un lancement du jeu via MO2."""
    enabled = len(enabled_mods(read_modlist(mo2.profile(profile))))
    log = latest_usvfs_log(mo2)

    if log is None:
        return UsvfsDiagnosis(
            active=False,
            checked_log=None,
            enabled_mod_count=enabled,
            message=_no_log_message(enabled),
        )

    text = system.read_text(log) or ""
    if usvfs_active_in(text):
        return UsvfsDiagnosis(
            active=True,
            checked_log=log,
            enabled_mod_count=enabled,
            message=_active_message(log, enabled),
        )

    message = _dead_no_mods_message() if enabled == 0 else _dead_message(log, enabled)
    return UsvfsDiagnosis(active=False, checked_log=log, enabled_mod_count=enabled, message=message)
