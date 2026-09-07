"""Du fichier nommé dans la trace au mod qui le fournit — **suspect**, pas coupable.

Le moteur ne nomme jamais un mod : il nomme un fichier, et parfois seulement une
ressource sans extension (« visual »). L'attribution consiste donc à retrouver,
sous `<install>/gamma/mods/`, quel dossier de mod fournit ce fichier.

Aucune deuxième attribution n'est écrite ici : la règle « sous `mods/`, le
premier segment du chemin relatif **est** le mod » appartient à
`integrity.report.mod_of`, et c'est elle qu'on appelle. Ce module n'ajoute que
la traduction « nom de ressource du moteur → chemin plausible sous `gamedata/` »,
qui, elle, n'existait nulle part.

## Ce que « suspect » veut dire, sur le cas réel qui a servi de banc d'essai

La session plantée mesurée s'arrête sur :

    ! error in stalker [sim_default_csky_2], profile [dick_…] with visual
    [actors\\stalker_nebo\\stalker_nebo3_exohead]
    stack trace:

Le fichier `gamedata/meshes/actors/stalker_nebo/stalker_nebo3_exohead.ogf`
existe bel et bien — fourni par le mod `29- Dux's Innemurable Characters Kit -
DuxFortis`. Et pourtant un **autre** mod (`31- Fixed Vanilla Models and Textures`)
fournit le reste du dossier `stalker_nebo/` sans ce fichier-là. Le mod nommé est
donc celui à **regarder en premier**, pas celui à accuser : le vrai fautif peut
être son voisin dans l'ordre de chargement. C'est exactement pour ça que le
rendu dit « suspect » et liste *tous* les propriétaires trouvés.

## Coût

`mods/` compte 761 dossiers sur une install GAMMA réelle, pour des centaines de
milliers de fichiers : parcourir l'arborescence est hors de question. On teste
donc l'existence de quelques chemins **construits** par mod (`os.stat`), et la
résolution insensible à la casse n'est tentée qu'en second passage, si le test
exact n'a rien donné nulle part.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from stalker_gamma_linux.integrity.report import mod_of
from stalker_gamma_linux.postmortem import markers

_GAMEDATA = "gamedata"


@dataclass(frozen=True, slots=True)
class AssetReference:
    """Une ressource nommée par le moteur, et les chemins où elle peut vivre."""

    raw: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Suspect:
    """Un mod qui fournit un fichier cité par la trace."""

    mod: str
    # Chemin relatif à `mods/`, donc préfixé du nom du mod : c'est la forme que
    # comprennent `integrity.report.mod_of` et le reste du projet.
    relative: str
    reference: str

    @property
    def within_mod(self) -> str:
        """Le chemin sans le nom du mod, pour un affichage qui ne le répète pas."""
        return self.relative[len(self.mod) + 1 :] if self.mod else self.relative


@dataclass(frozen=True, slots=True)
class Attribution:
    """Résultat de l'attribution : ce qu'on a trouvé, et ce qu'on n'a pas trouvé."""

    suspects: tuple[Suspect, ...] = ()
    # Ressources fournies par la base Anomaly elle-même, pas par un mod. C'est
    # une information, pas un échec : elle oriente vers le moteur ou vers une
    # partie corrompue plutôt que vers la liste de mods.
    base_game: tuple[str, ...] = ()
    # Ressources qu'on n'a su rattacher à rien. Le cas normal : la base Anomaly
    # livre l'essentiel de son contenu empaqueté dans `db/*.db*`, qu'on n'ouvre
    # pas — donc « introuvable sur le disque » ne veut pas dire « inexistant ».
    unattributed: tuple[str, ...] = ()

    @property
    def has_suspects(self) -> bool:
        return bool(self.suspects)


def _normalise(raw: str) -> str:
    return raw.strip().strip("'\"").replace("\\", "/").strip("/")


def _candidates_for(path: str) -> tuple[str, ...]:
    """Chemins relatifs à un dossier de mod où cette ressource pourrait vivre."""
    suffix = PurePosixPath(path).suffix.lower()
    if not suffix:
        # Ressource citée sans extension : c'est un « visual », donc un modèle.
        return (f"{_GAMEDATA}/{markers.VISUAL_ROOT}/{path}{markers.VISUAL_EXTENSION}",)
    if suffix in markers.NON_MOD_EXTENSIONS:
        return ()
    # Le chemin tel quel d'abord (il porte déjà son dossier racine quand il a été
    # capturé derrière un `gamedata\…`), puis reconstruit depuis l'extension.
    seen = [f"{_GAMEDATA}/{path}"]
    seen.extend(f"{_GAMEDATA}/{root}/{path}" for root in markers.EXTENSION_ROOTS.get(suffix, ()))
    return tuple(dict.fromkeys(seen))


def references(lines: Iterable[str]) -> tuple[AssetReference, ...]:
    """Ressources nommées dans les lignes fournies, dans l'ordre, sans doublon."""
    found: dict[str, AssetReference] = {}
    for line in lines:
        for pattern in (
            markers.VISUAL_REF_RE,
            markers.GAMEDATA_REF_RE,
            markers.SCRIPT_REF_RE,
        ):
            for match in pattern.finditer(line):
                path = _normalise(match.group("path"))
                key = path.lower()
                if not path or key in found:
                    continue
                candidates = _candidates_for(path)
                if candidates:
                    found[key] = AssetReference(raw=path, candidates=candidates)
    return tuple(found.values())


def _mod_directories(mods_dir: Path) -> tuple[Path, ...]:
    try:
        with os.scandir(mods_dir) as entries:
            return tuple(
                sorted(
                    (Path(entry.path) for entry in entries if entry.is_dir()),
                    key=lambda path: path.name,
                )
            )
    except OSError:
        return ()


def _resolve_case_insensitive(base: Path, relative: str) -> Path | None:
    """Descend `relative` sous `base` en ignorant la casse, composant par composant.

    Les mods viennent d'archives Windows dépaquetées sur un système de fichiers
    **sensible** à la casse : `Meshes/` et `meshes/` coexistent d'un mod à
    l'autre, et le moteur, lui, écrit tout en minuscules.
    """
    current = base
    for part in PurePosixPath(relative).parts:
        try:
            with os.scandir(current) as entries:
                match = next(
                    (entry for entry in entries if entry.name.lower() == part.lower()), None
                )
        except OSError:
            return None
        if match is None:
            return None
        current = Path(match.path)
    return current


def _owners(
    reference: AssetReference, mod_dirs: Sequence[Path], *, ignore_case: bool
) -> tuple[Suspect, ...]:
    suspects: list[Suspect] = []
    for mod_dir in mod_dirs:
        for candidate in reference.candidates:
            if ignore_case:
                found = _resolve_case_insensitive(mod_dir, candidate) is not None
            else:
                found = (mod_dir / candidate).exists()
            if not found:
                continue
            relative = f"{mod_dir.name}/{candidate}"
            suspects.append(
                # `mod_of` est l'unique endroit du projet qui décide à quel mod
                # appartient un chemin sous `mods/` : on l'appelle plutôt que de
                # reprendre `mod_dir.name`, pour que les deux ne divergent pas.
                Suspect(mod=mod_of(relative), relative=relative, reference=reference.raw)
            )
            break
    return tuple(suspects)


def attribute(
    found_references: Sequence[AssetReference], mods_dir: Path, *, anomaly: Path | None = None
) -> Attribution:
    """Attribue chaque ressource à son ou ses mods ; dit ce qui n'appartient à aucun."""
    mod_dirs = _mod_directories(mods_dir)
    suspects: list[Suspect] = []
    base_game: list[str] = []
    unattributed: list[str] = []

    for reference in found_references:
        owners = _owners(reference, mod_dirs, ignore_case=False)
        if not owners:
            owners = _owners(reference, mod_dirs, ignore_case=True)
        if owners:
            suspects.extend(owners)
        elif anomaly is not None and _in_base_game(reference, anomaly):
            base_game.append(reference.raw)
        else:
            unattributed.append(reference.raw)
    return Attribution(
        suspects=tuple(suspects),
        base_game=tuple(base_game),
        unattributed=tuple(unattributed),
    )


def _in_base_game(reference: AssetReference, anomaly: Path) -> bool:
    """Vrai si la ressource est posée à plat dans la base Anomaly.

    Faux ne veut pas dire « elle n'y est pas » : la base livre l'essentiel de son
    contenu empaqueté dans `db/*.db*`, qu'on n'ouvre pas ici. D'où le rendu
    prudent côté `report`.
    """
    return any((anomaly / candidate).exists() for candidate in reference.candidates)
