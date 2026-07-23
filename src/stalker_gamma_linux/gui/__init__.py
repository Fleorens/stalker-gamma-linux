"""GUI GTK4/libadwaita (T08), au-dessus de la même API que la CLI (`cli.py`).

Aucune logique métier ici : ce paquet consomme `orchestrator`/`mo2.session`/
`doctor`/`state` exactement comme la CLI, via `output.Reporter` et les
callbacks `on_progress`/`cancel_event` déjà exposés par ces modules.

Ce fichier reste volontairement vide de tout import : `viewmodel.py`,
`worker.py` et `prefs.py` ne dépendent pas de `gi` (PyGObject) et doivent
rester importables — et testables — sur une machine sans GTK4/libadwaita.
Seuls `app.py` et `windows/` importent `gi`.
"""
