#!/usr/bin/env python3
"""Vérification d'intégration légère contre les définitions G.A.M.M.A amont.

Utilisé par `.github/workflows/upstream-watch.yml` : exécute les étapes
non-graphiques du pipeline `gamma-launcher` sur un sous-ensemble minimal du
modpack (jamais Anomaly, jamais les ~700 mods complets — voir
`tasks/T10-ci-github-actions.md`) :

1. `doctor` (informatif seulement, jamais bloquant ici — un conteneur CI n'a
   ni Steam ni GPU, c'est attendu, voir `stalker_gamma_linux.doctor`).
2. Récupération de `modlist.txt` + `modpack_maker_list.txt` depuis
   `Grokitach/Stalker_GAMMA` via `raw.githubusercontent.com` (quelques dizaines
   de Ko, jamais le clone complet du dépôt qui pèse plusieurs centaines de Mo).
3. Parsing via `launcher.mods.read_mod_maker` (le vrai parseur de
   gamma-launcher : détecte une régression du format amont).
4. Téléchargement + installation "à blanc" (répertoire temporaire, jamais
   l'installation réelle) d'un petit sous-ensemble de mods ModDB — le chemin
   le plus fragile (mirroring ModDB + Cloudflare), d'où le sous-ensemble
   volontairement minimal pour ne pas se faire rate-limiter.

Sortie non nulle sur la première étape qui échoue.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from launcher.mods.installer.base import BaseInstaller

RAW_BASE = "https://raw.githubusercontent.com"
MODPACK_DATA_FILES = ("modlist.txt", "modpack_maker_list.txt")


def _log(step: str, message: str) -> None:
    print(f"[{step}] {message}", flush=True)


def run_doctor() -> None:
    from stalker_gamma_linux.doctor import run_doctor as _run_doctor

    _log("doctor", "rapport d'environnement (informatif, non bloquant dans ce conteneur) :")
    _run_doctor()


def fetch_modpack_data(repo: str, ref: str, modpack_data_dir: Path) -> None:
    modpack_data_dir.mkdir(parents=True, exist_ok=True)
    for filename in MODPACK_DATA_FILES:
        url = f"{RAW_BASE}/{repo}/{ref}/G.A.M.M.A/modpack_data/{filename}"
        _log("fetch", url)
        with urllib.request.urlopen(url, timeout=30) as response:
            (modpack_data_dir / filename).write_bytes(response.read())


def parse_modlist(modpack_data_dir: Path) -> list[BaseInstaller]:
    from launcher.mods import read_mod_maker

    mods = read_mod_maker(modpack_data_dir)
    if not mods:
        raise RuntimeError("read_mod_maker() n'a retourné aucune entrée — format modlist cassé ?")
    _log("parse", f"{len(mods)} entrées parsées (mods + séparateurs)")
    return mods


def download_install_subset(
    mods: list[BaseInstaller], cache_dir: Path, install_dir: Path, count: int
) -> None:
    from launcher.mods import ModDBInstaller

    # Mêmes exclusions que `FullInstall._install_mods()` en amont (gamma-launcher
    # install.py) : ces deux entrées sont des placeholders ModDB connus (archive
    # vide/invalide) que gamma-launcher lui-même saute toujours, pas une
    # régression de notre côté si on les inclut sans discernement.
    skip_names = {"164- Hunger Thirst Sleep UI 0.71 - xcvb"}
    skip_titles = {"FDDA Redone Fixes"}

    eligible = [
        m
        for m in mods
        if isinstance(m, ModDBInstaller)
        and m.downloader is not None
        and m.info.name not in skip_names
        and m.info.title not in skip_titles
    ]
    subset = eligible[:count]
    if not subset:
        raise RuntimeError("aucun mod ModDB éligible trouvé dans le sous-ensemble")

    cache_dir.mkdir(parents=True, exist_ok=True)
    install_dir.mkdir(parents=True, exist_ok=True)

    for mod in subset:
        label = mod.info.title or mod.info.name
        _log("download", f"{label} ...")
        mod.download(cache_dir, use_cached=True)
        _log("install", f"{label} -> {install_dir}")
        mod.install(install_dir)

    _log("subset", f"{len(subset)} mod(s) téléchargé(s) + installé(s) sans erreur")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Grokitach/Stalker_GAMMA")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--mod-count", type=int, default=2)
    parser.add_argument(
        "--cache-dir", type=Path, default=None, help="Répertoire de cache (réutilisable entre runs)"
    )
    parser.add_argument("--workdir", type=Path, default=None)
    args = parser.parse_args(argv)

    workdir: Path = args.workdir or Path(tempfile.mkdtemp(prefix="upstream-smoke-"))
    cache_dir: Path = args.cache_dir or (workdir / "cache")
    modpack_data_dir = workdir / "grok" / "G.A.M.M.A" / "modpack_data"
    install_dir = workdir / "mods"

    try:
        run_doctor()
        fetch_modpack_data(args.repo, args.ref, modpack_data_dir)
        mods = parse_modlist(modpack_data_dir)
        download_install_subset(mods, cache_dir, install_dir, args.mod_count)
    except Exception as error:
        _log("FAIL", f"{type(error).__name__}: {error}")
        return 1

    _log("OK", "toutes les étapes ont réussi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
