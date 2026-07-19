# T01 — Spec : installation manuelle documentée

**Modèle recommandé : Fable 5** (recherche web intensive + synthèse technique).
**Dépendances : aucune.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md` et
`docs/ARCHITECTURE.md` d'abord). Objectif : produire
`docs/INSTALL-MANUAL.md`, la **spécification de référence** de l'installation
manuelle de S.T.A.L.K.E.R. G.A.M.M.A. sur Linux avec **MO2 sous Proton**
(pas le mode flat/usvfs-workaround, qui ne sera qu'une annexe).

Recherche et croise ces sources (elles divergent, note les divergences) :
- https://github.com/Mord3rca/gamma-launcher (README + wiki + issues Linux)
- https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
- https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- https://github.com/Grokitach/Stalker_GAMMA/wiki (processus officiel Windows,
  pour connaître le comportement cible)
- Discussions récentes (Reddit r/stalker_gamma, ProtonDB Anomaly, issues
  GitHub 2025-2026) sur MO2 sous Proton.

Le document doit contenir, étape par étape avec les commandes exactes :
1. Prérequis système (paquets Fedora + Arch + Debian, espace disque 27 Go
   téléchargés / ~76 Go installés).
2. Installation d'Anomaly (archives ModDB, extraction, arborescence cible de
   `docs/ARCHITECTURE.md`).
3. Installation du modpack via `gamma-launcher` (commandes exactes, options).
4. Création du préfixe Proton-GE partagé + verbs winetricks requis
   (`vcrun2022`, `d3dcompiler_43/47`, `d3dx9/10/11_43`) — via umu et via
   protontricks (les deux variantes).
5. Configuration de MO2 : chemin Anomaly dans l'instance, profil G.A.M.M.A,
   lancement de `ModOrganizer.exe` dans le préfixe, exécution du jeu DX11.
6. Suppression de ReShade et pourquoi ; alternative vkBasalt.
7. Pièges connus (shader cache, chemins avec espaces, versions de Proton qui
   cassent USVFS) avec leur remède.

Critères d'acceptation : chaque étape a une commande vérifiable et un « comment
savoir que ça a marché » ; les incertitudes sont marquées `⚠ À VALIDER` plutôt
que devinées ; pas d'étape « magique » sans explication.
