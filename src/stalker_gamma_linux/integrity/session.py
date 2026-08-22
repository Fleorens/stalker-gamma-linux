"""Commande `verify [--repair]` : enchaîne référence, scan, diff, réparation.

Seul point d'entrée de la fonctionnalité, partagé mot pour mot par la CLI et
par la vue Diagnostic de la GUI (`output.Reporter` + `cancel_event`, comme le
reste du projet). La GUI n'en réimplémente rien : elle fournit un reporter qui
pousse vers ses widgets, et récupère le même code de retour.

Trois invariants portés ici :

1. **Premier passage = enregistrement, pas vérification.** Sans référence
   antérieure, il n'y a rien à comparer ; annoncer « aucun écart » laisserait
   croire qu'une vérification a eu lieu. On enregistre, on le dit, on s'arrête.
2. **Un scan annulé ne réécrit jamais la référence.** `scan.scan_tree` lève au
   lieu de retourner un résultat partiel, et l'écriture de la référence ne vit
   qu'après le scan — un `cancel_event` levé à mi-parcours laisse la référence
   précédente exactement où elle était.
3. **La reprise de référence après réparation est une étape à part.** Elle
   coûte un second scan complet et elle est annoncée comme telle. Sans elle,
   les mods qu'on vient de remettre en état ressortiraient « modifiés » au
   passage suivant, ce qui ruinerait la confiance dans la commande.
"""

from __future__ import annotations

import threading
from pathlib import Path

from stalker_gamma_linux import output, sizing
from stalker_gamma_linux.engine.errors import EngineCancelledError, EngineError
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.integrity import baseline, repair, scan
from stalker_gamma_linux.integrity import report as report_module
from stalker_gamma_linux.integrity.errors import (
    IntegrityCancelledError,
    IntegrityError,
    ModsDirectoryMissingError,
)
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.paths_safety import UnsafeWipeTargetError

_SCAN_PHASE = _("Hashing installed mods")
_REPAIR_PHASES: tuple[str, ...] = (
    _("Removing the damaged mods"),
    _("Reinstalling them with the engine"),
    _("Recording the new reference (second scan)"),
)


def verify_phase_labels(*, repair_damaged: bool = False) -> tuple[str, ...]:
    """Libellés des étapes de `run_verify`, alignés sur sa numérotation `n/total`.

    Exposé pour que la GUI dessine sa timeline sans redériver la liste (même
    contrat que `_install_phases` côté `orchestrator`).
    """
    return (_SCAN_PHASE, *_REPAIR_PHASES) if repair_damaged else (_SCAN_PHASE,)


def run_verify(
    target: Path | None = None,
    *,
    repair_damaged: bool = False,
    reporter: output.Reporter = output.console_reporter,
    cancel_event: threading.Event | None = None,
) -> int:
    """Vérifie les mods installés sous `target`. 0 si intact, 1 s'il y a des écarts.

    `repair_damaged` : retire les mods abîmés d'origine officielle, les fait
    reposer par le moteur, puis réenregistre la référence — 0 si la réparation
    est allée à son terme. `CANCELLED_EXIT_CODE` si `cancel_event` a été levé,
    la référence précédente restant alors intacte.
    """
    root = target if target is not None else DEFAULT_INSTALL_TARGET
    mods_dir = Mo2Paths.under(root).mods
    total = len(verify_phase_labels(repair_damaged=repair_damaged))

    reporter.header(_("Checking installed mods in {path}").format(path=mods_dir))
    try:
        return _verify(
            root,
            mods_dir,
            total=total,
            repair_damaged=repair_damaged,
            reporter=reporter,
            cancel_event=cancel_event,
        )
    except (IntegrityCancelledError, EngineCancelledError):
        reporter.warn(_("Cancelled — the previous reference was left untouched."))
        return CANCELLED_EXIT_CODE
    except (IntegrityError, EngineError, UnsafeWipeTargetError) as error:
        reporter.error(str(error))
        return 1


def _verify(
    root: Path,
    mods_dir: Path,
    *,
    total: int,
    repair_damaged: bool,
    reporter: output.Reporter,
    cancel_event: threading.Event | None,
) -> int:
    if not mods_dir.is_dir():
        raise ModsDirectoryMissingError(mods_dir)

    previous = baseline.read_baseline(root)
    reporter.step(f"1/{total}", _("Hashing installed mods (this takes a few minutes)…"))
    scanned = scan.scan_tree(mods_dir, reporter=reporter, cancel_event=cancel_event)
    _warn_unreadable(scanned, reporter=reporter)

    if previous is None:
        return _record_first_reference(root, scanned, reporter=reporter)

    result = _build_report(mods_dir, previous, scanned)
    reporter.progress(report_module.format_report(result))

    if result.is_intact:
        reporter.success(_intact_verdict(result))
        return 0
    if not repair_damaged:
        reporter.warn(
            _(
                "Damaged files detected. Repair the affected mods with:\n"
                "  stalker-gamma-linux verify --repair --target {root}"
            ).format(root=root)
        )
        return 1
    return _repair(root, result, total=total, reporter=reporter, cancel_event=cancel_event)


def _intact_verdict(result: report_module.IntegrityReport) -> str:
    """Verdict d'une install saine — en distinguant « identique » de « tes ajouts ».

    Sans cette distinction, un joueur qui a ajouté trois fichiers voyait une
    liste de différences suivie d'un message vert, sans qu'on lui dise
    clairement qu'aucune de ces différences n'est une avarie.
    """
    reminder = _(
        "Run this check again after an update, or the day the game starts "
        "misbehaving — that is when the comparison is worth something."
    )
    if result.is_clean:
        return reminder
    return (
        _("Nothing damaged — the only differences are files you added, and they stay put.")
        + "\n"
        + reminder
    )


def _warn_unreadable(scanned: scan.ScanResult, *, reporter: output.Reporter) -> None:
    if not scanned.unreadable:
        return
    details = "\n".join(f"  - {entry.relative}: {entry.reason}" for entry in scanned.unreadable)
    reporter.warn(
        _(
            "{count} file(s) could not be read — they are neither fingerprinted "
            "nor compared:\n{details}"
        ).format(count=len(scanned.unreadable), details=details)
    )


def _record_first_reference(
    root: Path, scanned: scan.ScanResult, *, reporter: output.Reporter
) -> int:
    """Premier passage : on enregistre, et on dit clairement qu'on n'a rien vérifié."""
    path = baseline.write_baseline(root, scanned.digests)
    reporter.success(
        _(
            "Reference recorded: {files} files, {size} GiB ({path}).\n"
            "No comparison was made this time — there was nothing to compare against.\n"
            "Run the check again to detect changes since now."
        ).format(
            files=scanned.file_count,
            size=f"{scanned.total_bytes / sizing.GIB:.1f}",
            path=path,
        )
    )
    return 0


def _build_report(
    mods_dir: Path, previous: baseline.ParsedBaseline, scanned: scan.ScanResult
) -> report_module.IntegrityReport:
    changed, added, removed = report_module.compare(previous.digests, scanned.digests)
    return report_module.IntegrityReport(
        mods_dir=mods_dir,
        changed=changed,
        added=added,
        removed=removed,
        unreadable=scanned.unreadable,
        scanned_files=scanned.file_count,
        scanned_bytes=scanned.total_bytes,
        unparsed_baseline_lines=previous.skipped,
    )


def _repair(
    root: Path,
    result: report_module.IntegrityReport,
    *,
    total: int,
    reporter: output.Reporter,
    cancel_event: threading.Event | None,
) -> int:
    upstream = repair.upstream_mod_names(Mo2Paths.under(root).instance)
    plan = repair.build_repair_plan(result, upstream)
    reporter.progress(repair.format_plan(plan))
    if plan.is_empty:
        reporter.warn(
            _(
                "Nothing can be repaired automatically: none of the damaged mods "
                "comes from the modpack, or they hold files you added. They are "
                "listed above, untouched — repair them from Mod Organizer 2."
            )
        )
        return 1

    reporter.step(f"2/{total}", _("Removing the damaged mods…"))
    removed = repair.remove_mods(root, plan.repairable, reporter=reporter)

    reporter.step(f"3/{total}", _("Reinstalling them with the engine…"))
    repair.reinstall_mods(root, reporter=reporter, cancel_event=cancel_event)

    # Étape à part entière, et coûteuse (un second scan complet) : sans elle,
    # les mods qu'on vient de remettre en état ressortiraient « modifiés » au
    # passage suivant.
    reporter.step(f"4/{total}", _("Recording the new reference (second scan)…"))
    rescanned = scan.scan_tree(
        Mo2Paths.under(root).mods, reporter=reporter, cancel_event=cancel_event
    )
    _warn_unreadable(rescanned, reporter=reporter)
    baseline.write_baseline(root, rescanned.digests)

    reporter.success(
        _("{count} mod(s) repaired and the reference re-recorded.\nRepaired: {names}").format(
            count=len(removed), names=", ".join(removed)
        )
    )
    return 0
