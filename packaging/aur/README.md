# Paquets AUR

Deux PKGBUILD prêts à publier :

| Dossier | Ce qu'il fait |
|---|---|
| `python-gamma-launcher/` | Le moteur amont, absent de PyPI **et** des dépôts Arch — dépendance obligatoire du suivant |
| `stalker-gamma-linux/` | Ce projet : les deux commandes, le launcher GTK, l'entrée de menu et l'icône |

## Ce qui a été vérifié

Construits sous podman (`archlinux:latest`, 2026-08-16) avec `makepkg -d`, à
partir de la release taguée :

- `python-gamma-launcher` produit `usr/bin/gamma-launcher` et son `dist-info` ;
- `stalker-gamma-linux` produit les deux commandes, l'entrée
  `usr/share/applications/stalker-gamma-linux-gui.desktop`, l'icône sous
  `usr/share/icons/hicolor/256x256/apps/` et la licence ;
- `check()` fait tourner la suite de tests pendant la construction. C'est elle
  qui a attrapé une pollution du logging entre tests — invisible sous pytest
  9.1 (machine de dev), fatale sous 9.0 (Arch).

`.SRCINFO` est généré par `makepkg --printsrcinfo` : l'AUR le refuse s'il ne
correspond pas au `PKGBUILD`.

## Un helper AUR est nécessaire

`python-gamma-launcher` dépend de `python-cloudscraper`, absent des dépôts
officiels, qui dépend lui-même de `python-js2py` (AUR aussi). `makepkg -s` ne
résout pas ces chaînes : l'installation passe par `paru -S stalker-gamma-linux`
ou `yay -S stalker-gamma-linux`, ce qui est l'usage normal de l'AUR. À
mentionner dans le README principal le jour de la publication.

## Publier — action manuelle, décision du mainteneur

Rien n'a été publié : déposer sur l'AUR engage un compte et réserve un nom sur
un dépôt public. Ça ne fait pas partie d'une construction.

> **Bloqué en amont depuis le 2026-08-22** : l'AUR a suspendu la création de
> comptes (vague de créations automatisées). Sans compte, pas de clé SSH, donc
> pas de dépôt — l'étape 1 ci-dessous est infaisable, et rien de ce qui est ici
> n'est en cause. C'est temporaire et non spécifique à nous.
>
> Deux choses à ne pas confondre : la pause bloque la **publication**, pas la
> **consommation** — installer depuis l'AUR (`paru`, `yay`, `git clone`) n'a
> jamais demandé de compte. Aucun utilisateur Arch n'est bloqué en attendant :
> `install.sh` couvre Arch, et la CI l'y exerce à chaque push.
>
> Les réouvertures sont annoncées sur la liste `aur-general` et le flux de news
> Arch. Ne pas scripter de sondage de la page d'inscription : la demande est
> explicite, et ça n'apprendra rien plus tôt que ces deux canaux.

```sh
# 1. Clé SSH déclarée sur https://aur.archlinux.org (Account → My Account → SSH keys)
# 2. La dépendance d'abord, sinon le paquet principal est ininstallable
git clone ssh://aur@aur.archlinux.org/python-gamma-launcher.git
cp packaging/aur/python-gamma-launcher/{PKGBUILD,.SRCINFO} python-gamma-launcher/
cd python-gamma-launcher && git add PKGBUILD .SRCINFO
git commit -m "Initial import: gamma-launcher 3.1" && git push

# 3. Puis le paquet principal, même procédure
git clone ssh://aur@aur.archlinux.org/stalker-gamma-linux.git
```

## À chaque release

1. `pkgver=` mis à jour ;
2. somme recalculée :
   `curl -sL https://github.com/Fleorens/stalker-gamma-linux/archive/vX.Y.Z.tar.gz | sha256sum` ;
3. `makepkg --printsrcinfo > .SRCINFO` ;
4. construction de vérification (`makepkg -d`), puis push sur le dépôt AUR.
