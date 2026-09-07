"""Rendu du post-mortem — dire ce qu'on a lu, et rien de plus.

Deux règles de rédaction, toutes deux dictées par ce que le journal permet
réellement d'affirmer :

- un mod nommé dans une trace est un **suspect**, pas un coupable. Le moteur
  nomme un fichier ; le mod qui fournit ce fichier peut aussi bien être celui
  qui *manquait* d'une variante, ou celui qu'un autre écrase dans l'ordre de
  chargement. Le rendu le dit à chaque fois, pas une fois en bas de page ;
- un journal absent, tronqué ou muet donne « je ne peux pas conclure » **et le
  chemin du fichier**, jamais une hypothèse. L'utilisateur peut alors regarder
  lui-même, ce qui est plus utile qu'une supposition présentée comme un fait.
"""

from __future__ import annotations

from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.postmortem.attribution import Attribution, Suspect
from stalker_gamma_linux.postmortem.outcome import SessionEnd
from stalker_gamma_linux.postmortem.result import Finding, Postmortem

_COMPAT_DOC = "docs/MO2-PROTON-COMPAT.md"


def headline(postmortem: Postmortem) -> str:
    """La conclusion en une phrase — c'est elle que reprend le rapport d'issue."""
    finding = postmortem.finding
    if finding is Finding.LAUNCH_FAILURE:
        return _("The game did not start: the launch failed before the engine ran.")
    if finding is Finding.OUT_OF_MEMORY:
        return _("The engine stopped after failing to allocate memory (out of memory).")
    if finding is Finding.ENGINE_CRASH:
        return _("The engine crashed: its log stops on a fatal block, with no clean shutdown.")
    if finding is Finding.USVFS_INACTIVE:
        return _("The mods do not look mounted (USVFS): the game may have started without them.")
    if finding is Finding.CLEAN_SESSION:
        return _("Last session ended normally — no crash to report.")
    if finding is Finding.NO_ENGINE_LOG:
        if postmortem.engine_log is None:
            return _("No engine log found: I cannot tell how the last session ended.")
        # Le fichier est là mais vide — un journal remis à zéro, ou un moteur qui
        # n'a rien eu le temps d'écrire. Le dire, plutôt que « aucun journal »,
        # évite d'envoyer l'utilisateur chercher un fichier qu'il a sous les yeux.
        return _("The engine log is empty: I cannot tell how the last session ended.")
    return _(
        "The engine log ends without a shutdown or a crash: I cannot conclude "
        "(the game may still be running, or it was killed from outside)."
    )


def _session_lines(session: SessionEnd | None) -> list[str]:
    if session is None or session.started_at is None:
        return []
    if session.engine_build is None:
        return [_("Session started: {stamp}").format(stamp=session.started_at)]
    return [
        _("Session started: {stamp} (xrCore build {build})").format(
            stamp=session.started_at, build=session.engine_build
        )
    ]


def _suspect_lines(suspects: tuple[Suspect, ...]) -> list[str]:
    if not suspects:
        return []
    lines = [
        "",
        _(
            "Mods to look at first — SUSPECTS, not proof: they provide a file named "
            "in the trace. The culprit may be a mod that overrides one of them."
        ),
    ]
    for suspect in suspects:
        lines.append(f"  - {suspect.mod or _('(loose files under mods/)')}")
        lines.append(
            _("      {path}  (named as: {reference})").format(
                path=suspect.within_mod, reference=suspect.reference
            )
        )
    return lines


def _unattributed_lines(attribution: Attribution) -> list[str]:
    lines: list[str] = []
    if attribution.base_game:
        lines.append("")
        lines.append(_("Also named, and provided by the Anomaly base rather than a mod:"))
        lines.extend(f"  - {reference}" for reference in attribution.base_game)
    if attribution.unattributed:
        lines.append("")
        lines.append(
            _(
                "Named in the trace but provided by no installed mod. That is "
                "information, not a failure: the Anomaly base ships most of its "
                "content packed in db/, which is not opened here."
            )
        )
        lines.extend(f"  - {reference}" for reference in attribution.unattributed)
    return lines


def _no_suspect_line(postmortem: Postmortem) -> list[str]:
    if postmortem.attribution.has_suspects:
        return []
    return [
        "",
        _(
            "No mod could be named: the trace does not mention a file that any "
            "installed mod provides. The excerpt below is what there is to go on."
        ),
    ]


def _excerpt_lines(postmortem: Postmortem) -> list[str]:
    if not postmortem.excerpt:
        return []
    return [
        "",
        _("Excerpt kept from the engine log:"),
        *(f"  {line}" for line in postmortem.excerpt),
    ]


def _advice_lines(postmortem: Postmortem) -> list[str]:
    finding = postmortem.finding
    if finding is Finding.LAUNCH_FAILURE and postmortem.launch_failure is not None:
        return ["", postmortem.launch_failure]
    if finding is Finding.USVFS_INACTIVE and postmortem.usvfs is not None:
        return ["", postmortem.usvfs.message]
    if finding is Finding.OUT_OF_MEMORY:
        return [
            "",
            _(
                "→ Lower the texture/shader load (Screen Space Shaders, "
                "cumulative shader packs), and check that the machine is not "
                "short on RAM or swap while playing."
            ),
        ]
    if finding is Finding.ENGINE_CRASH:
        return [
            "",
            _(
                "→ Disable the suspects above one at a time in Mod Organizer 2, "
                "then replay the same scene. `stalker-gamma-linux verify` also "
                "tells you whether one of those mods is damaged on disk rather "
                "than merely incompatible."
            ),
        ]
    if finding is Finding.CLEAN_SESSION and postmortem.usvfs is not None:
        # Confirmation utile : « rien à signaler » ne dit pas si les mods
        # étaient bien montés, et c'est la question suivante du joueur.
        return ["", postmortem.usvfs.message]
    if finding is Finding.NO_ENGINE_LOG:
        return [
            "",
            _(
                "→ Launch the game once with `stalker-gamma-linux play`, close it, "
                "and run this command again. The engine writes its log under "
                "<anomaly>/appdata/logs/ (see {doc})."
            ).format(doc=_COMPAT_DOC),
        ]
    return []


def format_postmortem(postmortem: Postmortem) -> str:
    """Rendu texte complet, dans le vocabulaire de `doctor`."""
    lines = [headline(postmortem), ""]
    if postmortem.engine_log is not None:
        lines.append(_("Engine log: {path}").format(path=postmortem.engine_log))
    else:
        lines.append(_("Engine log: none found under <anomaly>/appdata/logs/"))
    if postmortem.launch_log is not None:
        lines.append(_("Launch log: {path}").format(path=postmortem.launch_log))
    lines.extend(_session_lines(postmortem.session))

    if postmortem.finding in (Finding.ENGINE_CRASH, Finding.OUT_OF_MEMORY):
        lines.extend(_suspect_lines(postmortem.attribution.suspects))
        lines.extend(_no_suspect_line(postmortem))
        lines.extend(_unattributed_lines(postmortem.attribution))
        lines.extend(_excerpt_lines(postmortem))
    lines.extend(_advice_lines(postmortem))
    return "\n".join(lines).rstrip("\n") + "\n"
