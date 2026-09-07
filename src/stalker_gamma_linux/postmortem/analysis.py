"""Assemblage du post-mortem : quel diagnostic l'emporte, et pourquoi.

Trois sources sont lues, toutes après coup — le jeu doit être fermé :

1. le **journal de lancement** (`logs/mo2-game.log` ou `flat-game.log`), pour
   les échecs qui surviennent avant que le moteur ne démarre ;
2. le **journal du moteur** X-Ray, pour la fin de la session elle-même ;
3. le **journal USVFS** de l'instance MO2, pour le cas « le jeu a bien tourné,
   mais sans les mods ».

## Le cas particulier qui justifie un test de fraîcheur

Un échec de lancement l'emporte sur tout le reste : si le processus n'a pas
démarré, il n'a pas pu planter. Sauf que deux des marqueurs reconnus par
`mo2.diagnostics` ne sont **pas fatals** — `docs/MO2-PROTON-COMPAT.md` le
documente, mesuré en T16 : Proton écrit `Prefix has an invalid version?!` puis
lance le jeu quand même. Appliqué mécaniquement, l'ordre de priorité ferait
alors disparaître le crash réel derrière un « reconstruis ton préfixe » — le
faux positif que le document annonçait comme « à traiter côté T14 ».

Le fait qui tranche est vérifiable sans rien supposer : **le moteur a-t-il
tourné pendant ce lancement ?** Le journal de lancement et celui du moteur sont
écrits pendant la même session ; si celui du moteur date d'il y a trois heures
alors que le lancement vient d'échouer, il décrit une autre partie et on l'ignore.
On ne compare donc pas des messages, on compare des dates de modification.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.mo2 import diagnostics
from stalker_gamma_linux.mo2.diagnostics import UsvfsDiagnosis
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.mo2.session import resolve_anomaly
from stalker_gamma_linux.postmortem import attribution, logfile
from stalker_gamma_linux.postmortem.outcome import SessionEnd, SessionOutcome, analyse
from stalker_gamma_linux.postmortem.result import Finding, Postmortem
from stalker_gamma_linux.prefix.paths import PrefixPaths

# Écart toléré entre la dernière écriture du journal de lancement et celle du
# journal du moteur pour les considérer comme décrivant la même partie. Large,
# parce que les deux fichiers ne sont pas écrits au même rythme (Wine se tait
# pendant qu'on joue) ; largement inférieur, en revanche, à l'écart qui sépare
# deux parties.
_SAME_SESSION_SECONDS = 300.0


def _mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def describes_same_session(engine_log: Path | None, launch_log: Path | None) -> bool:
    """Le journal du moteur décrit-il bien le lancement que raconte `launch_log` ?

    Sans journal de lancement à comparer, on fait confiance au journal du moteur
    (il n'y a rien qui le contredise).
    """
    engine_mtime = _mtime(engine_log)
    if engine_mtime is None:
        return False
    launch_mtime = _mtime(launch_log)
    if launch_mtime is None:
        return True
    return engine_mtime >= launch_mtime - _SAME_SESSION_SECONDS


def _engine_started(session: SessionEnd | None) -> bool:
    """Le moteur a-t-il atteint son `Game started:` ?"""
    return session is not None and session.started_at is not None


def _attribute(session: SessionEnd, mods: Path, anomaly: Path) -> attribution.Attribution:
    """Ressources nommées dans l'extrait de crash, rattachées à leurs mods.

    On ne cherche que dans l'extrait retenu : une ressource citée trois heures
    avant la chute n'est pas un suspect, c'est du bruit — le journal mesuré en
    contient des milliers.
    """
    lines = [*session.excerpt, *(value for _field, value in session.fatal_fields)]
    return attribution.attribute(attribution.references(lines), mods, anomaly=anomaly)


def build_postmortem(target: Path | None = None) -> Postmortem:
    """Analyse la dernière session de jeu de l'installation `target`."""
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    mo2 = Mo2Paths.under(root)
    prefix = PrefixPaths.under(root)
    anomaly = resolve_anomaly(mo2, InstallPaths.under(root))

    launch_log = diagnostics.latest_launch_log(prefix)
    launch_failure = diagnostics.diagnose_launch_log(launch_log)

    engine_log = logfile.find_engine_log(logfile.candidate_log_dirs(anomaly, mo2.overwrite))
    session: SessionEnd | None = None
    if engine_log is not None:
        loaded = logfile.load_engine_log(engine_log)
        if not loaded.is_empty:
            session = analyse(loaded.head, loaded.tail)

    fresh = describes_same_session(engine_log, launch_log)
    attributed = attribution.Attribution()
    usvfs: UsvfsDiagnosis | None = None

    # 1. Le lancement lui-même a échoué — sauf si le moteur a démarré malgré le
    #    marqueur (cas non fatal documenté), auquel cas ce n'est pas l'histoire
    #    de cette partie.
    if launch_failure is not None and not (fresh and _engine_started(session)):
        finding = Finding.LAUNCH_FAILURE

    # 2. et 3. La session elle-même, telle que le moteur l'a laissée.
    elif session is not None and fresh and session.outcome.is_failure:
        finding = (
            Finding.OUT_OF_MEMORY
            if session.outcome is SessionOutcome.OUT_OF_MEMORY
            else Finding.ENGINE_CRASH
        )
        attributed = _attribute(session, mo2.mods, anomaly)

    else:
        # 4. Quelque chose a tourné, mais peut-être sans les mods. Encore
        #    faut-il qu'il ait tourné : sur une install où personne n'a jamais
        #    joué, il n'y a ni journal du moteur ni journal USVFS, et conclure
        #    « les mods n'étaient pas montés » affirmerait plus qu'on ne lit.
        usvfs = diagnostics.diagnose_usvfs(mo2)
        ran = session is not None or usvfs.checked_log is not None
        if ran and not usvfs.active:
            finding = Finding.USVFS_INACTIVE
        # 5. Rien d'anormal — encore faut-il avoir lu quelque chose.
        elif session is None:
            finding = Finding.NO_ENGINE_LOG
        elif session.outcome is SessionOutcome.CLEAN_EXIT and fresh:
            finding = Finding.CLEAN_SESSION
        else:
            finding = Finding.INCONCLUSIVE

    return Postmortem(
        finding=finding,
        root=root,
        engine_log=engine_log,
        launch_log=launch_log,
        launch_failure=launch_failure,
        session=session,
        attribution=attributed,
        usvfs=usvfs,
    )
