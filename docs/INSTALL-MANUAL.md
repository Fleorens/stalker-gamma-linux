# Installation manuelle de S.T.A.L.K.E.R. G.A.M.M.A. sur Linux — spécification de référence

> **Rôle de ce document** : c'est la procédure manuelle complète que
> `stalker-gamma-linux` doit automatiser (mode principal : **MO2 sous
> Proton**). Chaque étape donne les commandes exactes et un critère de
> vérification. Les points incertains sont marqués `⚠ À VALIDER` — à
> confirmer sur machine réelle avant d'automatiser.
>
> Rédigé le 2026-07-19 à partir des sources croisées listées en fin de
> document. Guide de référence principal : gist de v1ld (mis à jour sept.
> 2025, méthode protontricks + Steam).

## 0. Vue d'ensemble

```
gamma-launcher (Python) ──► télécharge Anomaly + les ~400 mods (ModDB/GitHub)
                            et construit l'instance MO2 dans gamma/
Steam + Proton          ──► exécute ModOrganizer.exe (jeu non-Steam)
protontricks            ──► injecte les DLL Windows requises dans le préfixe
MO2 (sous Proton)       ──► lance Anomaly avec les mods montés via USVFS
```

Points clés validés par les sources :
- MO2 + USVFS **fonctionnent** sous Proton (avec un surcoût CPU connu) ;
  c'est la méthode recommandée par tous les guides récents.
- Le préfixe utilisé est celui créé par Steam pour le jeu non-Steam
  `ModOrganizer.exe` → MO2 et le jeu partagent naturellement le même préfixe.
- ReShade doit être retiré (incompatible DXVK) — étape obligatoire.

### Divergences notables entre les sources

| Sujet | v1ld (2025, réf.) | FaithBeam wiki | maxastyler (Deck, ancien) |
|---|---|---|---|
| Verbs winetricks | `d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 dx8vb quartz vcrun2022` (+`cmd` optionnel) | `d3dcompiler_43 d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 vcrun2022` | `d3dcompiler_43 d3dcompiler_47 d3dx10 d3dx11_43 d3dx9 d3dx9_43` |
| Proton | Proton **9/10 vanilla** via Steam | proton-ge-9-20 | non précisé |
| Outil préfixe | protontricks (prefix Steam) | winetricks/protontricks | protontricks (Discover) |
| Espace disque | 17 + 83 + 46 Go ≈ **146 Go** | n/a | n/a |

Décisions pour l'automatisation : partir du **surensemble des verbs**
(`d3dcompiler_43 d3dcompiler_47 d3dx9 d3dx10 d3dx11_43 dx8vb quartz
vcrun2022`) puis élaguer par tests (`⚠ À VALIDER` : dx8vb/quartz
réellement nécessaires ?). Proton vanilla 9/10 par défaut — plusieurs
retours signalent des soucis MO2 avec certaines versions GE
(`⚠ À VALIDER` : matrice précise → tâche T05).

---

## 1. Prérequis système

### Espace disque

| Dossier | Taille (sept. 2025) |
|---|---|
| `anomaly/` (jeu de base) | ~17 Go |
| `gamma/` (MO2 + mods) | ~83 Go |
| `cache/` (archives téléchargées) | ~46 Go |
| **Total pendant l'installation** | **~146 Go** |

Le chiffre officiel « 27 Go téléchargés / 76 Go installés » (wiki Grokitach)
est sous-estimé pour notre pipeline car le cache est conservé pour les
mises à jour. Le cache peut être purgé après install si l'espace manque
(mais toute mise à jour retéléchargera).

### Paquets requis

Fedora :
```bash
sudo dnf install python3 python3-virtualenv p7zip p7zip-plugins unrar protontricks
# unrar est dans RPM Fusion ; sinon libunrar via https://www.rarlab.com
```

Arch :
```bash
sudo pacman -S python python-virtualenv p7zip protontricks
yay -S libunrar        # AUR
```

Debian/Ubuntu :
```bash
sudo apt install python3 python3-venv p7zip-full libunrar5 protontricks
# ⚠ À VALIDER : nom exact du paquet libunrar selon la version de Debian/Ubuntu
```

Plus : **Steam** (natif de préférence ; Flatpak fonctionne mais protontricks
doit alors être le Flatpak `com.github.Matoking.protontricks` et les accès
disque étendus avec Flatseal — `⚠ À VALIDER`).

**Vérification** : `protontricks --version`, `7z`, `python3 --version`
(≥ 3.10) répondent ; `df -h` montre ≥ 150 Go libres sur la cible.

### Matériel
- GPU Vulkan fonctionnel (`vulkaninfo --summary` liste un device).
- 16 Go de RAM recommandés (8 Go = swap conseillé pendant l'install).

---

## 2. Installation de gamma-launcher

Trois méthodes (par ordre de préférence pour l'automatisation) :

**a) venv + pip (recommandée, reproductible)** :
```bash
git clone https://github.com/Mord3rca/gamma-launcher
cd gamma-launcher
git checkout <dernier tag de release>      # ex. v3.1 — épingler, pas master
python3 -m venv .venv && source .venv/bin/activate
pip install setuptools                     # requis Python ≥ 3.12
pip install .
```

**b) Binaire de release** (autonome, buildé sur Ubuntu) : télécharger depuis
https://github.com/Mord3rca/gamma-launcher/releases, `chmod +x`.
Piège connu : erreur `symbol lookup` sur certaines distros → lancer avec
`LD_PRELOAD=/usr/lib/libreadline.so ./gamma-launcher`.

**c) AUR** (Arch) : `yay -S gamma-launcher`.

**Vérification** : `gamma-launcher --help` liste les sous-commandes
(`anomaly-install`, `full-install`, `check-md5`, …).

---

## 3. Arborescence et installation d'Anomaly

```bash
mkdir -p ~/Games/stalker-gamma/{anomaly,gamma,cache}
gamma-launcher anomaly-install --anomaly ~/Games/stalker-gamma/anomaly
```

Le launcher télécharge Anomaly 1.5.1 + patch 1.5.2 depuis ModDB (gros
téléchargement, reprise possible en relançant).

⚠ Règle absolue : **chemins sans espaces ni caractères spéciaux** (les
chemins traversent la frontière Linux→Windows via Wine ; les espaces sont
une source classique de casse).

**Vérification** :
```bash
gamma-launcher check-anomaly --anomaly ~/Games/stalker-gamma/anomaly
ls ~/Games/stalker-gamma/anomaly/AnomalyLauncher.exe   # doit exister
```

---

## 4. Installation du modpack G.A.M.M.A.

```bash
gamma-launcher full-install \
  --anomaly ~/Games/stalker-gamma/anomaly \
  --gamma   ~/Games/stalker-gamma/gamma \
  --cache-directory ~/Games/stalker-gamma/cache
```

Ce que fait cette commande : récupère la définition du modpack
(Grokitach/Stalker_GAMMA + api stalker-gamma.com), résout les liens ModDB,
télécharge ~400 archives dans le cache, les extrait selon les directives
d'installation, et construit l'instance MO2 dans `gamma/` (mods, profils,
`ModOrganizer.exe`).

C'est long (dépend du débit ; ModDB rate-limite). **Interruption = pas
grave** : relancer la même commande reprend sur le cache.

Pièges connus :
- `ModDB download link not found` (issue #167 amont) : miroir mort côté
  ModDB, généralement corrigé en amont — mettre à jour gamma-launcher et
  relancer.
- Python 3.14 : bug d'extraction py7zr sur les grosses archives
  (contournement documenté dans les commentaires du gist v1ld).

**Vérification** :
```bash
gamma-launcher check-md5 --gamma ~/Games/stalker-gamma/gamma   # 0 erreur
ls ~/Games/stalker-gamma/gamma/ModOrganizer.exe
ls ~/Games/stalker-gamma/gamma/profiles/                        # profil G.A.M.M.A présent
```

---

## 5. Retrait de ReShade (obligatoire)

ReShade (injecté par le modpack pour Windows) ne fonctionne pas sous
DXVK/Proton et casse le rendu ou le lancement :

```bash
gamma-launcher remove-reshade --anomaly ~/Games/stalker-gamma/anomaly
gamma-launcher purge-shader-cache --anomaly ~/Games/stalker-gamma/anomaly
```

Équivalent cosmétique côté Linux si besoin : **vkBasalt** (hors périmètre
install, à documenter côté utilisateur).

**Vérification** : plus de `ReShade*.dll` / `reshade-shaders/` dans
`anomaly/bin/` ; `anomaly/appdata/shaders_cache/` vide ou absent.

---

## 6. Jeu non-Steam + préfixe Proton

### 6.1 Ajout à Steam
1. Steam → *Ajouter un jeu* → *Ajouter un jeu non Steam* → parcourir vers
   `~/Games/stalker-gamma/gamma/ModOrganizer.exe`.
2. Propriétés de l'entrée → *Compatibilité* → cocher *Forcer l'utilisation
   d'un outil de compatibilité* → **Proton 9 ou 10 (vanilla)**.
3. Lancer une fois l'entrée depuis Steam (MO2 peut s'afficher ou non),
   puis quitter : ce premier lancement **crée le préfixe**.

**Vérification** : un nouveau dossier
`~/.steam/steam/steamapps/compatdata/<APPID>/pfx/` est apparu (APPID
négatif/grand nombre = jeu non-Steam ; `protontricks -l` l'affiche).

### 6.2 Injection des DLL Windows

```bash
protontricks -l          # repérer l'APPID de "ModOrganizer.exe" / du raccourci
protontricks <APPID> d3dcompiler_43 d3dcompiler_47 d3dx9 d3dx10 d3dx11_43 \
                     dx8vb quartz vcrun2022
```

Notes :
- Ne **pas** installer `dxvk` via winetricks (Proton l'embarque déjà).
- Avertissements de hash SHA sur `vcrun2022` : ignorables (source amont).
- `cmd` est listé par v1ld mais échoue parfois → optionnel, skipper si erreur.
- `⚠ À VALIDER` : `dx8vb`/`quartz` (présents chez v1ld uniquement) et
  `d3dcompiler_43` (absent chez v1ld) — tester le sous-ensemble minimal.

**Vérification** :
```bash
ls ~/.steam/steam/steamapps/compatdata/<APPID>/pfx/drive_c/windows/system32/d3dcompiler_47.dll
```

### 6.3 Variante sans Steam (umu-launcher) — voie cible pour l'automatisation

`⚠ À VALIDER en entier` : aucun guide publié ne documente GAMMA via umu, mais
c'est la voie scriptable (pas de clic dans Steam, préfixe à l'emplacement
qu'on choisit) :

```bash
# principe attendu :
WINEPREFIX=~/Games/stalker-gamma/prefix GAMEID=umu-stalkergamma \
  PROTONPATH=GE-Proton umu-run ~/Games/stalker-gamma/gamma/ModOrganizer.exe
# + verbs via : umu-run winetricks <verbs>  (protonfixes embarque winetricks)
```

Si validée, cette variante devient le chemin principal de `stalker-gamma-linux`
(T04) et l'ajout Steam se fait ensuite par `shortcuts.vdf` (T06).

---

## 7. Configuration de Mod Organizer 2

Relancer l'entrée Steam (MO2 s'ouvre dans le préfixe équipé) :

1. Si MO2 demande le type d'instance : **instance portable** (l'instance
   livrée par GAMMA dans `gamma/` est portable).
2. MO2 signale que le chemin d'Anomaly est invalide (normal : l'instance a
   été construite hors Wine) → désigner le dossier du jeu :
   `Z:\home\<user>\Games\stalker-gamma\anomaly` (les chemins Linux sont vus
   via le lecteur `Z:` dans le préfixe).
   Comportement connu : MO2 enchaîne dossier du jeu → dossier d'instance
   sans confirmation explicite — c'est normal, instance = `gamma/`.
3. Vérifier en haut à droite que le profil actif est **G.A.M.M.A** et que
   l'exécutable sélectionné est **Anomaly (DX11)** (ou
   `AnomalyLauncher.exe` dans le panneau de droite selon la version de
   l'instance).

Automatisation visée (T05) : écrire ces valeurs directement dans les `.ini`
de l'instance MO2 (`ModOrganizer.ini` : `gamePath`, exécutables, profil)
pour supprimer toute interaction.

**Vérification** : la colonne de gauche de MO2 liste les ~400 mods GAMMA,
cochés, sans triangle d'avertissement bloquant.

---

## 8. Premier lancement du jeu

1. Dans MO2 : exécutable **Anomaly (DX11)** → *Run*.
2. Premier lancement long (compilation shaders DXVK) — ne pas tuer le
   process avant plusieurs minutes.
3. Dans le menu principal : vérifier la présence du menu/HUD GAMMA (preuve
   que USVFS monte bien les mods — un Anomaly vanilla au lancement =
   USVFS mort, voir §9).

Réglages recommandés premier run : renderer DX11, plein écran fenêtré
d'abord (alt-tab plus sûr sous Wine), puis plein écran.

**Vérification finale** : nouvelle partie se charge en zone de départ ;
l'écran ne présente pas d'artefacts massifs (sinon → §5 ReShade/shaders).

---

## 9. Pièges connus et remèdes

| Symptôme | Cause probable | Remède |
|---|---|---|
| Le jeu se lance **vanilla** (pas de contenu GAMMA) | USVFS ne monte pas (version Proton incompatible) | Changer de version Proton (9/10 vanilla) ; matrice → T05 ; dernier recours : mode flat (annexe A) |
| Crash/écran noir au lancement | ReShade encore présent | §5 (`remove-reshade` + `purge-shader-cache`) |
| Artefacts visuels, shaders cassés | Cache shaders obsolète après update | `purge-shader-cache` + supprimer `anomaly/appdata/shaders_cache` |
| Perfs médiocres sur gros mods shaders (surtout Deck) | Screen Space Shaders / Shaders Cumulative Pack trop lourds | Désactiver ces mods dans MO2 (source : guide maxastyler) |
| `ModDB download link not found` pendant full-install | Miroir ModDB mort | Mettre à jour gamma-launcher, relancer (cache conservé) |
| MO2 ne démarre pas du tout | Verbs manquants dans le préfixe | Rejouer §6.2 ; vérifier vcrun2022 |
| Erreur `symbol lookup` avec le binaire release | libreadline embarquée | `LD_PRELOAD=/usr/lib/libreadline.so` |
| Casse aléatoire d'extraction (Python 3.14) | bug py7zr grosses archives | venv en Python 3.11–3.13, ou patch 7z système (gist v1ld) |
| Chemins avec espaces | traduction Wine des chemins | Réinstaller dans un chemin sans espaces |

Performance USVFS : le hooking Windows→Wine ajoute un surcoût CPU
(context-switching). Piste d'optimisation repérée : **RadTux** (VFS natif
Linux remplaçant les hooks USVFS de MO2) — expérimental, testé sur
Fallout 4/MO2 2.5.2, `⚠ À VALIDER` pour GAMMA → à évaluer en T05.

---

## Annexe A — Mode flat (fallback sans MO2)

Uniquement si MO2 refuse de fonctionner sur la config :

```bash
gamma-launcher usvfs-workaround \
  --anomaly ~/Games/stalker-gamma/anomaly \
  --gamma   ~/Games/stalker-gamma/gamma \
  --final   ~/Games/stalker-gamma/flat
```

Produit une installation fusionnée jouable sans MO2 (lancer
`AnomalyLauncher.exe` du dossier `flat/` sous Proton). **Perte de la
flexibilité mods** (plus d'activation/désactivation) — c'est un fallback,
pas le mode nominal de ce projet.

## Annexe B — Notes Steam Deck

- La procédure §1-8 s'applique (SteamOS a protontricks via Discover ;
  gamma-launcher en binaire release ou via distrobox — `⚠ À VALIDER` :
  le binaire Ubuntu tourne-t-il tel quel sur SteamOS ?).
- Installer sur microSD : possible mais chemins
  `/run/media/mmcblk0p1/...` — attention au formatage ext4/btrfs (pas de
  FAT : les liens/casse de noms cassent l'install).
- Perfs rapportées : ~60 FPS général, ~40 FPS base Clear Sky ; désactiver
  les mods shaders lourds (§9) améliore nettement.
- Mode Gaming : l'entrée non-Steam apparaît normalement ; prévoir un
  layout manette communautaire (SteamInputDB en propose pour GAMMA).

## Annexe C — Contexte : distribution GOG

Fin 2025, GOG a ajouté G.A.M.M.A. en « mod en un clic » via GOG Galaxy
(`⚠ À VALIDER` : périmètre exact — Galaxy est Windows-only, donc sans
impact direct pour Linux, mais cela crédibilise une distribution
« officielle » du modpack et pourrait offrir à terme une source de
téléchargement alternative à ModDB).

---

## Sources

- Gist v1ld (guide de référence, sept. 2025) :
  https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
- Mord3rca/gamma-launcher (moteur, commandes) :
  https://github.com/Mord3rca/gamma-launcher
- FaithBeam/stalker-gamma-cli wiki Linux :
  https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Wiki officiel GAMMA (comportement cible Windows) :
  https://github.com/Grokitach/Stalker_GAMMA/wiki/Installing-GAMMA
- Guide Steam Deck (maxastyler) :
  https://github.com/maxastyler/S.T.A.L.K.E.R.-Gamma-Steam-Deck-Install-Guide/
- USVFS sous Wine (thread compat MO2) :
  https://github.com/ModOrganizer2/modorganizer/issues/372
- RadTux (VFS natif expérimental pour MO2) :
  https://www.nexusmods.com/fallout4/mods/105285
- GOG one-click GAMMA (GamingOnLinux, déc. 2025) :
  https://www.gamingonlinux.com/2025/12/gog-add-stalker-gamma-as-a-one-click-mod-install/
