# T04 — Gestion du préfixe Proton

**Modèle recommandé : Fable 5 (ou Opus 4.8)** — territoire Wine/Proton peu
documenté, beaucoup de pièges.
**Dépendances : T02.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `docs/INSTALL-MANUAL.md`).

Objectif : module `prefix/` qui crée et entretient le préfixe Proton **unique
et partagé** (MO2 + jeu) décrit dans l'architecture.

1. Détection/téléchargement de Proton-GE : trouver les versions installées
   (Steam `compatibilitytools.d`, umu), sinon télécharger la release GE
   recommandée (vérification checksum) dans le bon dossier.
2. Création du préfixe dans `<install>/prefix/` via **umu-launcher** en voie
   principale (scriptable hors Steam) avec fallback protontricks documenté.
3. Application idempotente des verbs winetricks : `vcrun2022`,
   `d3dcompiler_43`, `d3dcompiler_47`, `d3dx9`, `d3dx10`, `d3dx11_43` —
   détecter ce qui est déjà installé, ne réappliquer que le manquant, gérer
   les échecs winetricks avec un message clair.
4. Fonction `run_in_prefix(exe, args, env)` réutilisable (T05/T06/T07
   s'appuieront dessus) : lance un exécutable Windows dans le préfixe avec les
   bonnes variables (`WINEPREFIX`/`GAMEID`/`PROTONPATH` selon umu), logs
   capturés dans un fichier.
5. Commande `prefix-doctor` : vérifie l'état du préfixe (verbs présents,
   version Proton, DXVK actif) et sait le réparer.

Contraintes : idempotence totale (relancer ne casse jamais un préfixe sain) ;
toute commande externe échouée = exception typée avec le log joint ; tests
avec subprocess mocké.

Critères d'acceptation : sur une machine réelle, deux exécutions successives
donnent le même état ; `ruff`/`mypy`/`pytest` passent.
