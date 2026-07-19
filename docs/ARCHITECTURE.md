# Architecture

## Principe

Trois couches. On ne réécrit que ce qui est spécifique à Linux.

```
┌─────────────────────────────────────────────┐
│  GUI (GTK4/libadwaita) — phase 3            │
├─────────────────────────────────────────────┤
│  stalker-gamma-linux (ce repo)              │
│  - CLI orchestrateur (install/update/play)  │
│  - Détection environnement & prérequis      │
│  - Gestion préfixe Proton (umu, Proton-GE,  │
│    verbs winetricks)                        │
│  - MO2 sous Proton (mode principal)         │
│  - Intégration Steam (shortcuts.vdf)        │
│  - Packaging (Flatpak/AppImage/AUR)         │
├─────────────────────────────────────────────┤
│  Moteur : Mord3rca/gamma-launcher (GPL-3.0) │
│  - Résolution miroirs ModDB, téléchargement │
│  - Parsing modlist GAMMA, directives        │
│  - anomaly-install, full-install, update,   │
│    check-md5                                │
└─────────────────────────────────────────────┘
```

## Décisions actées

1. **Option B** : wrapper au-dessus de `gamma-launcher`, pas de réécriture du
   moteur. On bénéficie de la maintenance amont quand le modpack change.
2. **MO2 sous Proton est le mode principal** (décision utilisateur) : c'est ce
   qui marche aujourd'hui et c'est ce qui préserve la flexibilité des mods
   (activer/désactiver/ajouter). Le mode « flat » (`usvfs-workaround`) n'est
   qu'un fallback documenté pour les configs où MO2 ne tourne pas.
3. **Préfixe unique** : MO2 et le jeu vivent dans le *même* préfixe Proton.
   MO2 lance `AnomalyLauncher.exe`/le jeu à travers son USVFS, donc les deux
   doivent partager le prefix. Verbs requis : `vcrun2022`, `d3dcompiler_43`,
   `d3dcompiler_47`, `d3dx9`, `d3dx10`, `d3dx11_43`.
4. **Proton-GE via umu-launcher** de préférence à protontricks quand possible :
   fonctionne hors Steam, scriptable, reproductible.
5. **ReShade est retiré** (incompatible DXVK) ; vkBasalt proposé en équivalent.
6. **Python** partout (cohérence avec le moteur), packaging `pyproject.toml`.
7. **Jamais de rehosting** : le repo ne contient que du code. Tous les
   téléchargements (Anomaly, mods) se font côté client depuis ModDB/GitHub.

## Arborescence cible d'une installation

```
~/Games/stalker-gamma/            # configurable
├── prefix/                       # préfixe Proton partagé (MO2 + jeu)
├── anomaly/                      # jeu de base (archives ModDB)
├── gamma/                        # MO2 + mods + profils GAMMA
│   ├── ModOrganizer.exe
│   ├── mods/
│   └── profiles/G.A.M.M.A/
└── cache/                        # archives téléchargées (reprise/update)
```

## Références

- Moteur : https://github.com/Mord3rca/gamma-launcher
- Modpack : https://github.com/Grokitach/Stalker_GAMMA (AGPL-3.0)
- API modlist : https://stalker-gamma.com/api/list
- Guide historique : https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Gist d'install manuelle : https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
