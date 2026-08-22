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
| MO2 **ne démarre pas du tout**, journal de lancement mentionnant `concrt140.dll`, `msvcp140.dll` ou `vcruntime140.dll` | Runtimes VC++ 2015-2022 manquants dans le préfixe (verbs non posés, ou préfixe bricolé/partiellement réparé) | `stalker-gamma-linux prefix-doctor --repair` (repose les verbs manquants). |
| Erreur Wine illisible au lancement : `wine client error:0: version mismatch`, `wrong wineserver`, `prefix has an invalid version`, `your wine binary was not upgraded correctly` | Le préfixe partagé a été construit par une **autre version de Proton** que celle configurée. Ce n'est **pas** un problème de sélection du `wineserver` (mesuré, cf. « `WINESERVER` sous umu ») : c'est le contrôle de version du préfixe par Proton | `stalker-gamma-linux install --only prefix` (reconstruit le préfixe à partir de zéro avec le Proton actuellement configuré). |
| Perfs médiocres (gros mods shaders) | Surcoût USVFS + shaders lourds | Désactiver Screen Space Shaders / Shaders Cumulative Pack ; évaluer RadTux (`⚠ À VALIDER`). |

Détection (`mo2/diagnostics.py`) : `diagnose_launch_log` lit le journal de
lancement umu-run (`prefix.process`, `logs/mo2-game.log` de l'install — voir
« Lancement détaché du terminal » ci-dessous pour ce nom fixe) à la recherche
des deux échecs **en amont** de l'USVFS ci-dessus (runtime VC++ manquant,
préfixe d'une autre version de Proton) — recherche insensible à la casse. Si
l'un des deux est reconnu, son message de remède doit être affiché **à la
place** du diagnostic USVFS (un utilisateur à qui on annonce deux problèmes
n'en corrige aucun) : ces échecs empêchent le process cible de démarrer, donc
l'USVFS n'a de toute façon jamais eu la moindre chance de monter.

> Depuis T15 (`play` détaché, voir plus bas), `run_play` **n'appelle plus ces
> fonctions automatiquement** : le jeu tourne encore quand `play` rend la
> main, donc les lire à ce moment-là serait un faux négatif systématique
> (rien n'a encore eu le temps de s'écrire). `diagnose_launch_log`/
> `diagnose_usvfs` restent utilisables **après coup**, une fois le jeu fermé
> (T14 de `docs/ROADMAP.md`, pas encore câblé en commande dédiée) — c'est
> pour ça que `play` annonce désormais le chemin du journal au lieu de le
> diagnostiquer lui-même.

Sinon, on lit le dernier `logs/usvfs-*.log` de l'instance et on cherche les
marqueurs d'un **VFS vivant** relevés sur un vrai run qui fonctionne (usvfs
0.5.6.1, GE-Proton11-1) : `inithooks in process <pid> successful` (hooks posés
dans le process du jeu) et `mapping file in vfs:` (le VFS sert effectivement des
fichiers). Absents ⇒ avertissement (pas un échec : `play` réussit si le jeu
s'est lancé). On vérifie aussi que le profil `G.A.M.M.A` a des mods activés
(`modlist.txt`, lignes `+`).

> Le marqueur `proxy run successful` cité par des guides de forum **n'existe
> pas** dans usvfs 0.5.6.1 : l'avoir utilisé donnait un faux négatif (constaté
> en réel le 2026-07-22).

## Lancement détaché du terminal (T15, 2026-08-22)

**Qualification.** Trois chemins de lancement du jeu, examinés séparément :

1. Entrée `.desktop` « Play GAMMA (direct) » (`desktop/entry.py`) : `Terminal=false`,
   pas de terminal contrôleur à fermer — **non concernée**, par construction.
2. GUI (`gui/worker.py`) : l'opération tourne dans un thread démon **du même
   process** que la fenêtre GTK ; fermer la fenêtre ne signale rien au
   process enfant (umu-run/Wine), qui n'est de toute façon lancé sans
   terminal contrôleur quand la GUI part de son `.desktop` — **non concernée**.
3. `stalker-gamma-linux play` en ligne de commande : **c'était le cas
   problématique**. `prefix.process.run_in_prefix` lançait `Popen` sans
   `start_new_session` : l'enfant héritait de la session/du groupe de
   processus du terminal appelant. Reproduit avec un pseudo-terminal
   (`os.forkpty` + fermeture du côté maître, qui envoie SIGHUP au groupe de
   processus au premier plan de la session — même mécanisme qu'un terminal
   qu'on ferme) : le process enfant **mourait** dans la seconde.

**Correctif.** `prefix.process.run_detached()` (nouvelle fonction sœur de
`run_in_prefix`, dédiée aux lancements de *jeu*) : `start_new_session=True`,
`stdin=DEVNULL`, sortie redirigée directement dans un fichier de log unique
par lancement (`logs/mo2-game.log` / `logs/flat-game.log`, plus d'horodatage
par lancement), tourné (1 backup `.log.1`) au-delà de 5 Mio, descripteur
refermé côté parent dès le retour de `Popen`. `mo2.launch.launch_game` et
`mo2.flat.launch_flat` l'utilisent désormais ; `mo2.launch.launch_mo2`
(interface MO2 seule, commande `mo2`) et tout le pipeline d'installation
(`engine`/`prefix.provision`) restent sur `run_in_prefix`, bloquant avec
progression/`cancel_event` — deux modes explicites, jamais un mode qui devine
lequel il est.

**Revalidé en conditions réelles** (2026-08-22, install de test complète
`/mnt/games_lexar/Games/GAMMA-test`, umu 1.4.1, GE-Proton11-3), même méthode
que la qualification (`os.forkpty` + fermeture du côté maître = même
mécanisme SIGHUP qu'un vrai terminal qu'on ferme), mais contre le vrai `play`
lançant le vrai MO2/Anomaly :

- **Premier essai, avec `start_new_session=True` seul (sans `stdin=DEVNULL`)** :
  échec. `play` rend bien la main immédiatement (mode détaché OK), mais
  fermer le terminal juste après a tué **toute** la sandbox umu-run
  (`srt-bwrap`, Proton, wineserver, MO2, le jeu) quelques secondes après son
  lancement. Cause identifiée par inspection des process (`ps -eo
  pid,ppid,sid,pgid,tty,stat`) : `run_detached` héritait quand même du
  `stdin` du terminal appelant (rien ne le redirigeait) ; la sandbox interne
  d'umu-run (`srt-bwrap`, steam-runtime/pressure-vessel) fait elle-même un
  `setsid()` puis reprend ce descripteur comme **son propre** terminal de
  contrôle via `TIOCSCTTY` — possible car la session d'origine devient
  orpheline dès que `play` a rendu la main (plus aucun process vivant dedans).
  `bwrap` se retrouvait donc process de premier plan du pseudo-terminal :
  fermer celui-ci lui envoyait SIGHUP, qui tuait toute la sandbox en dessous —
  le symptôme qu'on croyait avoir corrigé, reproduit un étage plus bas, à
  l'intérieur même d'umu-run.
- **Avec le correctif complet (`stdin=subprocess.DEVNULL` ajouté)** : succès.
  Même scénario rejoué à l'identique (même install, `play` relancé) : après
  fermeture simulée du terminal, toute la chaîne (`umu-run` → `srt-bwrap` →
  `pv-adverb` → `proton` → `wineserver` → `explorer.exe`/`ModOrganizer.exe`
  (`main`) → **`AnomalyDX11.exe`**, le moteur du jeu) est restée vivante et a
  continué à progresser (le jeu a fini de démarrer *après* la fermeture
  simulée). Aucun process de la chaîne n'a plus de terminal de contrôle
  (`tty=?` partout dans `ps`).

Conséquence sur `play` : la commande ne bloque plus jusqu'à la fermeture du
jeu, elle annonce le chemin du journal et rend la main immédiatement. Le
diagnostic USVFS automatique après lancement (`--no-diagnose`) a été retiré
en même temps — il n'avait plus de sens en mode détaché (voir plus haut).

## `WINESERVER` sous umu — question tranchée (T16, 2026-08-22)

**Question posée.** Quand MO2 lance le jeu à travers l'USVFS, un `wineserver`
système (`/usr/bin/wineserver`, présent sur cette machine : `wine-core-11.0-3.fc44`)
ou celui d'un Proton plus ancien peut-il être sélectionné à la place de celui du
Proton du préfixe ? Un client et un serveur Wine dépareillés produisent exactement
le `version mismatch` que le diagnostic de lancement apprend à reconnaître. La
parade connue sur un `proton run` Steam direct est d'imposer
`WINESERVER=<proton>/files/bin/wineserver` — mais ce n'est pas notre chemin : nous
passons par `umu-run`, qui gère son propre runtime.

**Réponse : non. Aucun découplage n'existe sur ce chemin, et `WINESERVER` n'a pas
à être imposé.** `_prefix_environment` reste inchangé — c'est la question tranchée
qui a de la valeur, pas un patch. Le détail ci-dessous documente *pourquoi* c'est
structurel et pas une chance, pour qu'on n'ait pas à reposer la question.

### Méthode de mesure (reproductible)

Le point décisif est de **ne pas se fier aux variables d'environnement seules** :
elles disent ce qui a été *demandé*, pas quel binaire a *gagné*. Pour chaque
process de la chaîne dont `/proc/<pid>/environ` pointe sur le préfixe partagé, on
relève donc les deux :

- `WINESERVER`, `WINELOADER`, `PROTONPATH` (dans `/proc/<pid>/environ`) ;
- **`readlink /proc/<pid>/exe`** — le binaire réellement exécuté, seul verdict.

Trois lancements réels sur l'install de test (`/mnt/games_lexar/Games/GAMMA-test`,
umu 1.4.1), chacun jusqu'à `AnomalyDX11.exe` vivant, en imposant `PROTONPATH` via
le code du projet (`mo2.launch.launch_game`) — donc le vrai chemin MO2 →
`moshortcut://` → USVFS → jeu, pas un banc synthétique. Le préfixe a été
sauvegardé avant et restauré après (les lancements le réécrivent, voir plus bas).

### Relevés

Préfixe construit par **GE-Proton11-3**. `AnomalyDX11.exe` atteint dans les trois cas.

| Lancement | Proton imposé | Base Wine | `WINESERVER` | `wineserver` réellement exécuté | Loader de MO2 **et** du jeu | `/usr/bin/wineserver` utilisé |
|---|---|---|---|---|---|---|
| 1 | GE-Proton11-3 (= celui du préfixe) | 11.0 | ∅ non posé | `GE-Proton11-3/files/bin/wineserver` | GE-Proton11-3 | non |
| 2 | **GE-Proton9-20** (plus ancien que le préfixe) | 9.0 | ∅ non posé | `GE-Proton9-20/files/bin/wineserver` | GE-Proton9-20 | non |
| 3 | GE-Proton11-1 (après le 9-20) | 11.0 | ∅ non posé | `GE-Proton11-1/files/bin/wineserver` | GE-Proton11-1 | non |

Dans les trois cas, **un seul dist Proton dans toute la chaîne** (13, 11 et 14
process respectivement : `wineserver`, `services.exe`, `explorer.exe`,
`ModOrganizer.exe`, `AnomalyDX11.exe`…), et `WINESERVER` posé **nulle part** —
y compris sur le process enfant du jeu, là où le découplage était supposé se
produire. Aucun `version mismatch` ni `wrong wineserver` sur aucun des trois.

`WINELOADER` : non posé sous GE-Proton11-x (build wow64), posé par Wine lui-même
sous GE-Proton9-20 (`.../GE-Proton9-20/files/bin/wine64`) — cohérent avec le même
dist dans les deux cas.

### Pourquoi c'est structurel

Quatre couches, aucune ne laisse la place au découplage :

1. **umu ne pose jamais `WINESERVER`** : zéro occurrence de la chaîne dans
   l'intégralité du zipapp umu-launcher 1.4.1 (177 entrées). L'hypothèse de départ
   (« umu pose probablement déjà un `WINESERVER` cohérent ») est donc fausse dans
   sa lettre — mais la conclusion tient pour une autre raison, la suivante.
2. **Proton ne le pose pas non plus** : zéro occurrence de `WINESERVER` dans son
   script `proton`. Il garde son `wineserver_bin` comme chemin interne
   (`files/bin/wineserver` relatif à son propre dist) et se contente de préfixer
   son `bin_dir` au `PATH`.
3. **Wine le dérive de lui-même.** `WINESERVER` non posé, `ntdll.so` résout le
   serveur **relativement au loader qui l'a chargé** (`server/wineserver` +
   `getenv("WINESERVER")` en surcharge optionnelle, visibles dans les symboles de
   `files/lib/wine/x86_64-unix/ntdll.so`). La `cmdline` du `wineserver` mesuré le
   montre littéralement :
   `…/GE-Proton11-3/files/lib/wine/../../bin/wineserver` — un chemin dérivé du
   `ntdll.so` chargé, ni un `PATH` ni une variable. Client et serveur viennent du
   même dist **par construction**.
4. **Le conteneur rend le wine hôte inatteignable.** Dans la sandbox umu
   (pressure-vessel, Steam Runtime 3/4), `/usr` de l'hôte est *remplacé* :
   `/usr/bin/wineserver` n'existe pas, `wineserver` n'est pas sur le `PATH`
   (`/usr/bin:/bin`). Le wine Fedora n'est visible qu'en `/run/host/usr/bin/wineserver`,
   chemin qu'aucun loader Wine ne consulte. Le scénario « le wineserver système est
   sélectionné » est donc **impossible** sous umu, pas seulement improbable.

### Pourquoi il ne faut pas poser `WINESERVER` « par sécurité »

Ce serait au mieux redondant, au pire nuisible : umu **réécrit** `PROTONPATH` dans
plusieurs cas (nom de code type `GE-Proton`, repli `UMU-Latest`, résolution du
runtime conteneur — `umu_run.py`, résolution de `PROTONPATH` avant lancement). Un
`WINESERVER` dérivé du `PROTONPATH` que *nous* passons pointerait alors sur un
autre dist que celui qu'umu finit par monter — ce qui **créerait** le découplage
que la variable était censée prévenir. La sélection actuelle est correcte parce
qu'elle est dérivée en bout de chaîne, par le loader effectivement chargé.

### Effet de bord mesuré : `Prefix has an invalid version?!` n'est pas fatal

Les lancements 2 et 3 ont fait tourner un Proton sur un préfixe construit par un
autre. Proton l'a détecté, l'a annoncé, puis **a continué** :

```
Proton: Upgrading prefix from GE-Proton11-3 to GE-Proton9-20 (…/prefix/)
Proton: Prefix has an invalid version?! You may want to back up user files and delete this prefix.
```

…et le jeu s'est lancé quand même, USVFS compris, en réécrivant le `version` du
préfixe au passage (d'où la sauvegarde/restauration dans la méthode). Deux
conséquences :

- Le `version mismatch` que reconnaît le diagnostic de lancement relève de la
  **version du préfixe**, pas de la sélection du `wineserver` : imposer
  `WINESERVER` n'y changerait rien. Le remède de la table ci-dessus
  (`install --only prefix`) reste le bon — un préfixe réécrit d'une base Wine à
  l'autre garde ses verbs et ses overrides posés pour l'autre.
- `prefix has an invalid version` fait partie des marqueurs de
  `mo2/diagnostics.py` (`_PREFIX_VERSION_MARKERS`), or il apparaît ici sur des
  lancements **réussis** : lu après coup, le diagnostic conclurait à un échec de
  préfixe alors que la partie a démarré. Faux positif connu, à traiter côté T14 —
  hors périmètre de cette tâche, qui ne touche pas au code.

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
- Sélection du `wineserver` sous umu (T16) : relevés `/proc/<pid>/environ` +
  `/proc/<pid>/exe` sur trois lancements réels (GE-Proton11-3, GE-Proton9-20,
  GE-Proton11-1) de l'install de test, 2026-08-22 — voir la section dédiée
  ci-dessus. Sources croisées : absence de `WINESERVER` dans le zipapp
  umu-launcher 1.4.1 et dans le script `proton` de GE-Proton11-3 ; résolution
  auto-relative du serveur par `ntdll.so`.
- pressure-vessel / Steam Runtime (le conteneur qui remplace `/usr` et rend le
  wine hôte inatteignable) :
  https://gitlab.steamos.cloud/steamrt/steam-runtime-tools/-/tree/main/pressure-vessel
</content>
</invoke>
