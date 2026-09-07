# Découpage des tâches

Chaque fichier est un **prompt autonome** à donner à Claude Code (nouvelle
session, dans le dossier du repo). L'ordre recommandé et le modèle le plus
adapté :

| # | Tâche | Modèle recommandé | Dépend de |
|---|-------|-------------------|-----------|
| T01 | Spec d'installation manuelle (recherche + doc) | **Fable 5** (recherche web + synthèse) | — |
| T02 | Squelette Python + détection environnement | **Sonnet 5** | T01 |
| T03 | Wrapper du moteur gamma-launcher | **Sonnet 5** | T02 |
| T04 | Gestion du préfixe Proton | **Fable 5** ou Opus 4.8 | T02 |
| T05 | MO2 sous Proton (le morceau dur) | **Fable 5** | T03, T04 |
| T06 | Raccourci bureau (`.desktop`) | **Sonnet 5** | T04, T05 |
| T07 | CLI orchestrateur | **Sonnet 5** | T03, T04, T05 |
| T08 | GUI GTK4/libadwaita | **Sonnet 5** | T07 |
| T09 | Packaging Flatpak / AppImage — ⚠ retiré du projet (2026-07-26) | **Sonnet 5** | T07 |
| T10 | CI GitHub Actions | **Sonnet 5** (itérations YAML : Haiku 4.5) | T07 |

### Phase 4 — Durcissement (issues de la revue du 2026-08-17)

| # | Tâche | Modèle recommandé | Dépend de | Priorité |
|---|-------|-------------------|-----------|----------|
| T11 | Garde-fous de chemin sur `uninstall --game-data` | **Sonnet 5** | T07 | 🔴 défaut de sûreté |
| T12 | Intégrité MD5 des mods installés + réparation | **Fable 5** | T03, T07 | 🟠 fonctionnalité |
| T13 | Verrou « MO2 / préfixe occupé » | **Sonnet 5** | T04, T05 | 🟠 perte de données |
| T14 | Diagnostic runtime/préfixe du log de lancement | **Sonnet 5** | T05 | 🟡 support |
| T15 | `play` détaché du terminal — ⚠ à qualifier d'abord | **Sonnet 5** | T05 | 🟡 confort |
| T16 | Épinglage `WINESERVER` sous umu — ✅ tranché (2026-08-22) : aucun découplage, pas de patch | **Fable 5** | T04, T05 | 🔵 tranché |

Ces six tâches sont issues d'une revue d'état de l'art menée le 2026-08-17
(autres outils de l'écosystème Linux/GAMMA). Quatre autres pistes examinées à
cette occasion ont été écartées : elles sont **déjà couvertes** chez nous —
contournement du rate-limit de l'API GitHub (`updates.py`, plus les replis
`FALLBACK_*` de `prefix/umu.py` et `prefix/download.py`), distinction
compat-data / `pfx` (`prefix/paths.py`), préservation des clés inconnues à
l'édition de `ModOrganizer.ini` (`mo2/ini.py`), et le packaging AppImage (hors
périmètre depuis T09).

Ordre conseillé : **T11 d'abord** (le seul point qui peut détruire des données
utilisateur, ~150 lignes avec ses tests), puis T13 (même famille), puis T12
qui est la vraie fonctionnalité manquante. T14/T15/T16 sont du polish, et deux
d'entre elles peuvent se conclure sans changement de code.

### Phase 5 — Adoption (issues de la revue du 2026-09-07)

Revue comparative avec le launcher Windows officiel. Constat de départ : le
launcher officiel a **trois boutons** (*First Install Initialization*,
*Install / Update GAMMA*, *Play*). Nous sommes déjà devant sur les
fonctionnalités. Ces six tâches ne rattrapent donc pas un retard : elles visent
ce que seul Linux permet, et les modes d'échec qui font abandonner.

| # | Tâche | Modèle recommandé | Dépend de | Priorité |
|---|-------|-------------------|-----------|----------|
| T17 | Sauvegarde/restauration + fusion de la modlist — ✅ livrée (2026-09-07) | **Opus 5**, effort maximal | T07, T12 | 🔴 perte de données utilisateur |
| T18 | Post-mortem de session : crash attribué au mod | **Opus 5**, effort élevé | T05, T12, T14 | 🟠 support |
| T19 | Steam / mode Gaming en un clic (`shortcuts.vdf`) | **Opus 5**, effort élevé | T06, T11 | 🟠 public Deck/Bazzite |
| T20 | MangoHud, gamescope/FSR, vkBasalt | **Opus 5**, effort maximal | T04, T05 | 🟠 avantage Linux |
| T21 | Cache de shaders conservé hors préfixe | **Sonnet 5**, effort moyen | T04, T05 | 🟡 première impression |
| T22 | Résilience ModDB : dépôt manuel, reprise ciblée | **Sonnet 5**, effort élevé | T03, T07, T12 | 🟠 installation bloquée |

Ordre conseillé : **T17 d'abord** — c'est la plainte n°1 de GAMMA toutes
plateformes (« *your modlist, settings, and mod settings will reset* », wiki
officiel), et nous en faisions déjà la moitié sans le savoir. ✅ Livrée le
2026-09-07 : paquet `backups/` (sauvegarde, inventaire, restauration,
rotation) et fusion à trois voies de `modlist.txt` à chaque update. Puis
**T18**, dont le code est écrit à 80 % et inutilisé depuis T15. Puis **T22**
(une install bloquée ne pardonne pas), **T19** et **T20** (le public qui
grossit), **T21** en dernier.

Deux tâches revoient une décision antérieure et doivent commencer par la relire :
**T19** revient sur le hors-scope `shortcuts.vdf` de T06, **T18** termine la
moitié laissée ouverte par T14.

Hors périmètre de ces fiches, mais identifié à la même revue : le frein
principal aujourd'hui n'est pas fonctionnel. Le dépôt est à **5 étoiles, 0
issue, 0 fork** — le produit est meilleur que la concurrence et personne ne le
sait. Les trois leviers sont un **paquet AUR puis COPR** (les raisons du retrait
de T09 — le sandbox contre Wine/Proton — ne s'appliquent pas à un paquet
natif), une **présence dans les guides Linux du wiki GAMMA et son Discord**, et
l'**i18n au-delà de en/fr** (ru/uk/pl/de : le workflow gettext est déjà en
place, c'est du volume, pas de la complexité).

## Règle de choix des modèles

Chaque fiche annonce un modèle **et un niveau d'effort** : à modèle égal,
c'est l'effort qui décide de la profondeur de raisonnement, et l'oublier revient
à ne rien avoir choisi.

- **Opus 5** : ce qui demande de la recherche, du raisonnement système ou du
  debug non documenté (Wine/Proton/USVFS, comportements de MO2, spec initiale).
  C'est là que le modèle le plus fort rapporte le plus.
  *Effort maximal* quand le résultat n'est pas connu d'avance (comportement à
  mesurer, données utilisateur irréversibles) ; *effort élevé* quand le problème
  est cerné mais dense.
- **Sonnet 5** : le développement bien cadré — une fois la spec écrite, ces
  tâches sont du code Python/YAML classique. Rapide et largement suffisant.
  *Effort élevé* s'il y a des cas limites à couvrir, *moyen* sinon.
- **Haiku 4.5** : retouches mécaniques (YAML de CI, doc, renommages).
- En cas de blocage sur une tâche Sonnet (bug Wine bizarre, comportement
  Proton non documenté) : repasser la session en Opus 5 à effort maximal plutôt
  que d'insister.

> Les fiches T01 à T16 mentionnent **Fable 5**, indisponible sur ce compte.
> C'est un état de fait à la date de leur rédaction, laissé tel quel : partout
> où elles le citent, lire « Opus 5 à effort maximal ».

## Hygiène commune à toutes les tâches

- Python ≥ 3.11, `pyproject.toml`, lint `ruff`, types `mypy`, tests `pytest`.
- Fichiers courts et cohésifs (200-400 lignes), pas de mutation d'objets,
  erreurs gérées explicitement, validation des entrées aux frontières.
- Aucun secret en dur ; aucun rehosting de contenu du jeu ou des mods.
- Commits : `<type>: <description>` (feat, fix, refactor, docs, test, chore).
