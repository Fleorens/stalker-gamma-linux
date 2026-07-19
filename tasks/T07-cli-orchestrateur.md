# T07 — CLI orchestrateur

**Modèle recommandé : Sonnet 5.**
**Dépendances : T03, T04, T05 (T06 optionnelle).**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md` et le code existant dans `src/`).

Objectif : assembler les modules en une CLI complète — c'est le livrable MVP
de la phase 1.

Commandes (framework : `click` ou `typer`, choisis et justifie) :
- `install` : doctor → chemins (défaut `~/Games/stalker-gamma`, flag
  `--path`) → anomaly → modpack → préfixe → config MO2 → (option
  `--steam`) → récap final. Reprise possible après interruption à chaque
  étape (état persisté dans un fichier de config TOML sous
  `~/.config/stalker-gamma-linux/`).
- `update` : mise à jour du modpack + re-vérification MD5 + rappel des
  étapes manuelles éventuelles.
- `play` : lance le jeu via MO2 (T05) ; `--mo2` pour ouvrir MO2 seul.
- `doctor` : rapport environnement (T02) + état préfixe (T04) + état
  install.
- `steam-add` (T06).
- Global : `--verbose`, logs fichier tournants dans
  `~/.local/state/stalker-gamma-linux/`, sortie propre et progression
  lisible (rich), erreurs toujours accompagnées d'une action suggérée.

Écris aussi un `install.sh` minimal à la racine (curl-able) qui : vérifie
python ≥ 3.11, crée un venv sous `~/.local/share/stalker-gamma-linux/`,
installe le paquet, et lance `install`. Pas de sudo dedans.

Critères d'acceptation : `stalker-gamma-linux install` enchaîne tout sur une
machine propre ; chaque commande a un `--help` clair ; interruption Ctrl-C
puis relance = reprise sans casse ; `ruff`/`mypy`/`pytest` passent ; mettre à
jour le README avec l'usage réel.
