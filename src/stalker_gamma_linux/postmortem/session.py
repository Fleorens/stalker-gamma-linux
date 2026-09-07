"""Commande `stalker-gamma-linux postmortem` : que s'est-il passé la dernière fois ?

À lancer **après** avoir fermé le jeu. C'est la moitié manquante du diagnostic :
depuis que `play` rend la main sans attendre (le jeu tourne encore), plus rien
ne lisait les journaux au moment où ils ont enfin quelque chose à dire.

Code de retour : 0 si la dernière session ne demande rien à l'utilisateur (fin
propre, ou verdict impossible), 1 si le post-mortem a trouvé quelque chose à
corriger — même convention que `doctor`, pour qu'un script puisse brancher.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.output import console
from stalker_gamma_linux.postmortem.analysis import build_postmortem
from stalker_gamma_linux.postmortem.report import format_postmortem


def run_postmortem(target: Path | None = None) -> int:
    postmortem = build_postmortem(target)
    # `markup=False` n'est pas une précaution de style : l'extrait de journal est
    # truffé de crochets (`[error]`, `[wpn_k98]`, `[sim_default_csky_2]`) que
    # `rich` lirait comme des balises — au mieux le texte disparaît, au pire
    # `MarkupError` interrompt la commande (voir la docstring d'`output.py`).
    # `soft_wrap` garde chaque ligne de journal sur une ligne : recopiée dans une
    # issue, une trace recoupée à la largeur du terminal ne se relit plus.
    console.print(format_postmortem(postmortem), markup=False, highlight=False, soft_wrap=True)
    return 1 if postmortem.finding.is_problem else 0
