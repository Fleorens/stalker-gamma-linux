"""Codes de sortie partagés par toutes les commandes.

Isolé dans son propre module parce que deux couches en ont besoin sans devoir
se connaître : `orchestrator` (install/update) et `mo2.session` (jouer/MO2).
Faire vivre la constante dans `orchestrator`, que `mo2.session` aurait importée,
créait un cycle — `orchestrator` importe déjà `mo2.session.resolve_anomaly`.
"""

from __future__ import annotations

# Convention POSIX (128 + SIGINT) : réutilisée pour toute annulation propre,
# qu'elle vienne d'un Ctrl-C de la CLI ou du `cancel_event` de la GUI.
CANCELLED_EXIT_CODE = 130
