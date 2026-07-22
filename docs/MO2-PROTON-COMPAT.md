# Matrice de compatibilité MO2 × Proton × USVFS (état de l'art 2025-2026)

> **Rôle de ce document** : arbitrer le choix de la version de Proton pour le
> **mode principal** de `stalker-gamma-linux` — Mod Organizer 2 tournant sous
> Proton avec **USVFS actif**, seul moyen de préserver la flexibilité des mods
> (activer/désactiver/ajouter) demandée par le projet.
>
> Il est référencé par le code : le diagnostic post-lancement
> (`mo2/diagnostics.py`) renvoie l'utilisateur ici quand il détecte un USVFS
> mort (jeu lancé « vanilla »). Rédigé le 2026-07-22 à partir des sources
> croisées listées en fin de document.

## TL;DR — recommandation

1. **Défaut du projet : la dernière release GE-Proton** (décision utilisateur
   2026-07-19, gérée par `prefix/`). Sur Wine 9/10, USVFS fonctionne dans la
   très grande majorité des cas — **validé en réel le 2026-07-22** avec
   **GE-Proton11-1** sur une install GAMMA complète (MO2 ouvert, 577 mods
   servis via USVFS, Anomaly DX11 lancé et joué).
2. **Si le jeu démarre en « vanilla » (0 mod, USVFS mort)** — symptôme n°1 de
   ce document — bascule sur **Proton 9.0 ou 10.0 *vanilla* de Steam** : c'est
   la combinaison la plus fiable et la plus rapportée pour USVFS + MO2. Le
   `prefix/` accepte déjà « Proton - Experimental » ; pour un GE/vanilla précis,
   pose-le dans `compatibilitytools.d` et relance.
3. **Ne jamais** rester sous **Proton ≤ 8.x / GE-Proton8-x** avec le MO2 2.5.x
   livré par GAMMA : ces builds sont **sous Wine 8.0**, antérieurs au correctif
   USVFS requis (voir « Pourquoi ça casse »). C'est le piège le plus courant.

Le mode **flat** (`gamma-launcher usvfs-workaround`, annexe A de
`INSTALL-MANUAL.md`) reste le dernier recours si aucune version de Proton ne
monte l'USVFS sur la machine — au prix de la flexibilité des mods.

## Pourquoi ça casse (racine technique)

MO2 ne copie pas les mods dans le jeu : il monte un **système de fichiers
virtuel local au processus** (USVFS, `usvfs_x64.dll`) par *API hooking* des
appels fichiers Windows. Seuls les processus lancés **depuis MO2** voient cet
overlay — d'où l'obligation de lancer le jeu *à travers* MO2 (`moshortcut://`),
et non l'exécutable directement.

Sous Wine/Proton, ce hooking exige des syscalls Windows récents que Wine n'a
implémentés que tardivement :

- **Wine bug 46697** : USVFS (MO2 ≥ 2.1.1) réclame
  `ntdll.NtQueryDirectoryFileEx` (syscall Windows 10 build 1709+). Les deux
  correctifs nécessaires ont d'abord atterri autour de **Wine 4.21**.
- **MO2 2.5.x** (la lignée livrée par GAMMA) va plus loin et exige un correctif
  supplémentaire **disponible seulement à partir de Wine 8.21** : en nov. 2023,
  *aucun* build Proton/GE ne l'embarquait encore, et SteamTinkerLaunch épinglait
  MO2 **2.4.4** en attendant. Ce correctif est aujourd'hui présent dans toute la
  lignée **Wine 9.x / 10.x**, donc dans **Proton 9.0, 10.0** et les GE-Proton
  correspondants.
- **Observé en réel (GE-Proton11-1, Wine 10, usvfs 0.5.6.1)** : usvfs échoue à
  hooker `NtQueryDirectoryFileEx` (`failed to hook NtQueryDirectoryFileEx: No
  Error`) mais **hooke l'ancien `NtQueryDirectoryFile`** et le VFS fonctionne
  parfaitement. Le correctif « Ex » de Wine 8.21 n'est donc pas strictement
  requis sur cette pile ; le hook de repli suffit à GAMMA.
- **Régressions propres à GE** : historiquement, USVFS a fonctionné sous le
  Proton *vanilla* de Valve tout en **échouant sur certains builds GE** (patchs
  additionnels de GE qui régressaient le hooking), *alors même* que le correctif
  Wine était présent. C'est exactement le scénario « le jeu se lance mais en
  vanilla » : Wine assez récent, mais VFS non monté. D'où la règle : GE par
  défaut, **repli sur Proton vanilla 9/10 si le diagnostic échoue**.

Surcoût connu : le hooking Windows→Wine ajoute un coût CPU (context-switching)
sensible sur les gros modpacks comme GAMMA. Piste native expérimentale :
**RadTux** (remplace les hooks USVFS par un démon VFS Linux) — hors périmètre,
`⚠ À VALIDER` pour GAMMA.

## Matrice

Statut : ✅ fonctionne · ⚠️ variable/à surveiller · ❌ cassé. « MO2 GAMMA »
désigne la lignée **2.5.x** empaquetée dans l'instance livrée par
gamma-launcher.

| MO2 | Proton / GE | Base Wine | USVFS | Notes & source |
|---|---|---|---|---|
| 2.5.x (GAMMA) | **Proton 10.0** (vanilla Steam) | 10.x | ✅ | Recommandé 2025 par les guides GAMMA (v1ld). Le plus fiable avec 9.0. |
| 2.5.x (GAMMA) | **Proton 9.0** (vanilla Steam) | 9.x | ✅ | « Proton 9.0 recommandé » (modorganizer2-linux-installer). Valeur sûre. |
| 2.5.x (GAMMA) | **Proton - Experimental** | 10.x+ | ⚠️ | Contient les derniers correctifs, mais bouge chaque semaine : peut casser puis se réparer. Accepté par `prefix/` en l'absence de GE. |
| 2.5.x (GAMMA) | **GE-Proton11-1** | 10.x | ✅ | **Validé en réel (2026-07-22)** : USVFS 0.5.6.1 monté, 577 mods servis, partie jouée. C'est le défaut du projet. |
| 2.5.x (GAMMA) | **GE-Proton10-x (dernier)** | 10.x | ⚠️→✅ | OK sur les builds récents ; en cas de « vanilla », repli vanilla 9/10. |
| 2.5.x (GAMMA) | **GE-Proton9-20** | 9.x | ✅ | Version GE explicitement citée comme fonctionnelle (wiki FaithBeam). Bon repli GE épinglé. |
| 2.5.x (GAMMA) | **GE-Proton8-x** | 8.0 | ❌ | Antérieur à Wine 8.21 → correctif MO2 2.5 absent. À éviter. |
| 2.5.x (GAMMA) | **Proton ≤ 8.0** (vanilla) | ≤ 8.0 | ❌ | Idem : MO2 2.5.x ne monte pas l'USVFS. Piège classique. |
| 2.4.4 | Proton 7/8 | 7–8 | ✅ | Combinaison de repli historique de SteamTinkerLaunch. Hors périmètre (GAMMA livre 2.5.x). |
| toute | Proton 5.0–9 (vanilla) | ≥ 4.21 | ✅ (jeux Bethesda) | USVFS OK sous Proton vanilla « mais pas les builds GE » à l'époque (rockerbacon). Illustre la régression GE. |

> Les cellules ⚠️ ne veulent pas dire « ne pas utiliser » : elles disent
> « laisse le diagnostic post-lancement décider et prépare le repli ». Le GE le
> plus récent est le défaut *justement* parce qu'il apporte les autres
> correctifs de jeu ; on ne renonce à lui que si USVFS ne monte pas.

## Symptôme → remède (utilisé par le diagnostic)

| Symptôme observé | Cause probable | Remède (par ordre) |
|---|---|---|
| Le jeu démarre mais **sans contenu GAMMA** (menu/HUD vanilla) ; le log USVFS de l'instance n'affiche pas `proxy run successful` | **USVFS mort** : version de Proton incompatible, ou jeu lancé hors MO2 | 1) Vérifier qu'on lance bien via `moshortcut://` (mode `play`, pas l'exe direct). 2) Passer en **Proton 9.0/10.0 vanilla**. 3) Essayer **GE-Proton9-20**. 4) Dernier recours : **mode flat** (`play --flat`). |
| MO2 s'ouvre mais **0 mod actif** | Mauvais dossier de jeu / profil, instance non configurée | Reconfigurer l'instance (`gamePath` → dossier Anomaly, profil `G.A.M.M.A`) — automatisé par `mo2/instance.py`. |
| MO2 **ne démarre pas du tout** | Verbs manquants dans le préfixe (vcrun2022…) | `stalker-gamma-linux prefix-doctor --repair` (T04). |
| Perfs médiocres (gros mods shaders) | Surcoût USVFS + shaders lourds | Désactiver Screen Space Shaders / Shaders Cumulative Pack ; évaluer RadTux (`⚠ À VALIDER`). |

Détection automatisée (`mo2/diagnostics.py`) : après un lancement via `play`,
on lit le dernier `logs/usvfs-*.log` de l'instance et on cherche les marqueurs
d'un **VFS vivant** relevés sur un vrai run qui fonctionne (usvfs 0.5.6.1,
GE-Proton11-1) : `inithooks in process <pid> successful` (hooks posés dans le
process du jeu) et `mapping file in vfs:` (le VFS sert effectivement des
fichiers). Absents ⇒ avertissement (pas un échec : `play` réussit si le jeu
s'est lancé). On vérifie aussi que le profil `G.A.M.M.A` a des mods activés
(`modlist.txt`, lignes `+`).

> Le marqueur `proxy run successful` cité par des guides de forum **n'existe
> pas** dans usvfs 0.5.6.1 : l'avoir utilisé donnait un faux négatif (constaté
> en réel le 2026-07-22).

## Sources

- MO2 — fil de compatibilité Linux/Wine USVFS (issue #372) :
  https://github.com/ModOrganizer2/modorganizer/issues/372
- usvfs (bibliothèque de hooking) :
  https://github.com/ModOrganizer2/usvfs
- Wine bug 46697 (USVFS ↔ `NtQueryDirectoryFileEx`, Win10 1709+) :
  https://bugs.winehq.org/show_bug.cgi?id=46697
- ValveSoftware/wine #67 — « Merge USVFS patch » :
  https://github.com/ValveSoftware/wine/issues/67
- SteamTinkerLaunch — wiki MO2 (MO2 2.5.0 exige Wine ≥ 8.21, repli 2.4.4) :
  https://github.com/sonic2kk/steamtinkerlaunch/wiki/Mod-Organizer-2
- modorganizer2-linux-installer (rockerbacon/Furglitch) — Proton 9.0
  recommandé ; « USVFS OK sous Proton vanilla mais pas les builds GE » :
  https://github.com/rockerbacon/modorganizer2-linux-installer ·
  https://github.com/Furglitch/modorganizer2-linux-installer/wiki/Post%E2%80%90Install-Instructions ·
  https://github.com/rockerbacon/lutris-skyrimse-installers/issues/156
- Guide GAMMA Linux (v1ld, réf. sept. 2025 — Proton 9/10, config MO2) :
  https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
- Wiki FaithBeam (GE-Proton9-20) :
  https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Guide Steam Deck (maxastyler) :
  https://github.com/maxastyler/S.T.A.L.K.E.R.-Gamma-Steam-Deck-Install-Guide/
- Marqueurs réels d'un VFS vivant (`inithooks in process N successful`,
  `mapping file in vfs:`) : relevés dans un `logs/usvfs-*.log` d'une install
  GAMMA fonctionnelle (usvfs 0.5.6.1, GE-Proton11-1), 2026-07-22. Le
  `proxy run successful` des guides Nexus/STEP ne s'y trouve pas.
- RadTux — VFS natif Linux expérimental pour MO2 :
  https://www.nexusmods.com/fallout4/mods/105285
</content>
</invoke>
