"""Fusion à trois voies de `modlist.txt` : garder les réglages du joueur à l'update.

`full-install` réécrit `profiles/G.A.M.M.A/modlist.txt` avec la liste amont
(`_install_modorganizer_profile` chez gamma-launcher). Trois choses distinctes
disparaissent : les mods **désactivés** par le joueur, l'**ordre** qu'il a
ajusté, et les mods qu'il a **ajoutés** lui-même. Ce module rejoue par-dessus
la nouvelle liste amont les seuls écarts qui lui sont imputables.

`base` = la liste amont de la mise à jour précédente (instantané pris juste
après que le moteur l'a écrite, voir `modlist_sync.py`), `ours` = le fichier du
joueur avant la mise à jour, `theirs` = la nouvelle liste amont.

## Ce qui est fusionné, et comment

**L'ordre et l'état sont deux problèmes séparés.** L'ordre est une suite de
noms ; l'état (`+` activé, `-` désactivé, `*` non géré) est une propriété de
chaque nom. Les mélanger produit les fusions subtilement fausses que cette
tâche existe pour éviter, parce qu'un mod déplacé *et* désactivé n'est pas
deux fois le même écart.

- **L'ordre** passe par un diff3 classique sur la suite des noms : les régions
  que le joueur n'a pas touchées prennent l'amont, celles que l'amont n'a pas
  touchées prennent le joueur, et **toute région modifiée des deux côtés prend
  l'amont** — en cas de doute, on ne fusionne pas.
- **L'état** se décide nom par nom : si le joueur l'a changé depuis `base`,
  c'est le sien ; sinon c'est celui de l'amont, qui a pu légitimement activer
  ou désactiver un mod dans la nouvelle version.

## Les règles qui n'ont rien d'évident

- `modlist.txt` se lit **de bas en haut** (priorité croissante vers le haut).
  Raisonner « ligne N » se trompe de sens un jour sur deux : ici rien n'est
  indexé en absolu, tout est positionné par rapport à des **voisins nommés**,
  ce qui garde le même sens quel que soit le bout par lequel on lit.
- Un mod **retiré en amont** n'est jamais ressuscité : son dossier n'existe
  plus sous `mods/`, MO2 l'afficherait en « missing ». L'ensemble des noms du
  résultat est contraint à `theirs ∪ (ours − base)`, et rien d'autre.
- Un mod **ajouté par le joueur** est réinséré auprès de son voisin conservé
  le plus proche, jamais empilé en fin de liste (voir `_insert_near_neighbour`).
- Les **séparateurs** (`…_separator`) sont des entrées comme les autres : ils
  participent à la fusion — c'est ce qui fait qu'un mod réinséré retombe dans
  la bonne section — mais ne sont pas comptés comme des mods dans le rapport.
- **En cas de doute, on ne fusionne pas** : `merge_modlists` retourne alors
  `merged=False` avec le motif, l'appelant garde l'amont et la sauvegarde. Une
  fusion silencieusement fausse est pire qu'une restauration manuelle.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from stalker_gamma_linux.i18n import _

_MARKERS = "+-*"
_SEPARATOR_SUFFIX = "_separator"
_CRLF = "\r\n"
_LF = "\n"


@dataclass(frozen=True, slots=True)
class ListedEntry:
    """Une ligne d'entrée : son marqueur et son nom, tels qu'écrits."""

    marker: str
    name: str

    @property
    def enabled(self) -> bool:
        return self.marker != "-"

    @property
    def is_separator(self) -> bool:
        return self.name.endswith(_SEPARATOR_SUFFIX)

    @property
    def line(self) -> str:
        return f"{self.marker}{self.name}"


@dataclass(frozen=True, slots=True)
class ParsedList:
    """Un `modlist.txt` décomposé, sans rien perdre de ce qu'il faut réécrire."""

    header: tuple[str, ...]
    entries: tuple[ListedEntry, ...]
    newline: str = _LF
    trailing_newline: bool = True
    # Lignes non vides qui ne sont ni un en-tête ni une entrée : MO2 n'en écrit
    # pas. Leur présence est le signal qu'on ne comprend pas ce fichier.
    stray: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(entry.name for entry in self.entries)

    @property
    def by_name(self) -> dict[str, ListedEntry]:
        return {entry.name: entry for entry in self.entries}

    @property
    def has_duplicates(self) -> bool:
        return len(set(self.names)) != len(self.names)


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    """Résultat de la fusion : le texte à écrire, ou le motif de l'abstention."""

    merged: bool
    text: str | None = None
    reason: str = ""
    reactivated: int = 0
    deactivated: int = 0
    reinserted: int = 0
    removed_upstream: int = 0
    kept_upstream_entries: int = 0
    order_merged: bool = True

    @property
    def changed_anything(self) -> bool:
        return bool(self.reactivated or self.deactivated or self.reinserted)

    @property
    def report(self) -> str:
        """Le compte rendu que lit le joueur : sans lui, il ne sait pas s'il doit vérifier."""
        lines = [
            _(
                "Mod list merged: {toggled} mod(s) re-enabled/disabled the way you had "
                "them ({reactivated} enabled, {deactivated} disabled), {reinserted} mod(s) "
                "you added put back in place, {removed} entry(ies) removed upstream not "
                "restored."
            ).format(
                toggled=self.reactivated + self.deactivated,
                reactivated=self.reactivated,
                deactivated=self.deactivated,
                reinserted=self.reinserted,
                removed=self.removed_upstream,
            )
        ]
        if self.kept_upstream_entries:
            lines.append(
                _(
                    "{count} entry(ies) you had removed from the list are back: upstream "
                    "still ships them, and dropping a line MO2 would re-add on its own "
                    "is not something this merge decides for you."
                ).format(count=self.kept_upstream_entries)
            )
        if not self.order_merged:
            lines.append(
                _(
                    "Load order: kept as upstream wrote it — your reordering and the "
                    "upstream one could not be reconciled without guessing."
                )
            )
        return "\n".join(lines)


def parse(text: str) -> ParsedList:
    """Décompose un `modlist.txt`. Ne juge rien, ne jette rien de significatif."""
    crlf = text.count(_CRLF)
    newline = _CRLF if crlf > text.count(_LF) - crlf else _LF
    trailing_newline = text.endswith((_LF, "\r"))
    header: list[str] = []
    entries: list[ListedEntry] = []
    stray: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and line[0] in _MARKERS and len(line) > 1:
            entries.append(ListedEntry(marker=line[0], name=line[1:]))
            continue
        if not line:
            continue  # ligne vide : ni information, ni anomalie
        if entries:
            stray.append(raw)
        else:
            header.append(raw)
    return ParsedList(
        header=tuple(header),
        entries=tuple(entries),
        newline=newline,
        trailing_newline=trailing_newline,
        stray=tuple(stray),
    )


def render(header: tuple[str, ...], entries: tuple[ListedEntry, ...], parsed: ParsedList) -> str:
    """Réécrit un fichier complet, avec les fins de ligne du fichier d'origine."""
    lines = [*header, *(entry.line for entry in entries)]
    text = parsed.newline.join(lines)
    if lines and parsed.trailing_newline:
        text += parsed.newline
    return text


def merge_modlists(base_text: str, ours_text: str, theirs_text: str) -> MergeOutcome:
    """Fusionne les trois versions. Retourne le texte à écrire, ou le motif du refus."""
    base, ours, theirs = parse(base_text), parse(ours_text), parse(theirs_text)

    refusal = _refusal_reason(base, ours, theirs)
    if refusal is not None:
        return MergeOutcome(merged=False, reason=refusal)

    base_names, ours_names, theirs_names = base.names, ours.names, theirs.names
    added_by_player = tuple(
        name for name in ours_names if name not in base_names and name not in theirs_names
    )
    allowed = set(theirs_names) | set(added_by_player)

    order, conflicted = _three_way_order(list(base_names), list(ours_names), list(theirs_names))
    order = _keep_first(name for name in order if name in allowed)
    order_merged = not conflicted and set(order) == allowed
    if not order_merged:
        # L'ordre amont est le seul repli qui ne puisse pas être faux : il est
        # complet par construction. Les ajouts du joueur y reviennent ensuite,
        # placés par voisinage.
        order = list(theirs_names)
    for name in added_by_player:
        if name not in order:
            _insert_near_neighbour(order, list(ours_names), name)

    entries, reactivated, deactivated = _merge_states(order, base.by_name, ours.by_name, theirs)
    ours_by_name = ours.by_name
    return MergeOutcome(
        merged=True,
        text=render(theirs.header, entries, theirs),
        reactivated=reactivated,
        deactivated=deactivated,
        reinserted=sum(1 for name in added_by_player if not ours_by_name[name].is_separator),
        removed_upstream=sum(
            1 for name in ours_names if name not in allowed and not ours_by_name[name].is_separator
        ),
        kept_upstream_entries=sum(
            1
            for entry in theirs.entries
            if entry.name in base_names and entry.name not in ours_names and not entry.is_separator
        ),
        order_merged=order_merged,
    )


def _refusal_reason(base: ParsedList, ours: ParsedList, theirs: ParsedList) -> str | None:
    """Les cas où l'on préfère garder l'amont plutôt que fusionner à l'aveugle."""
    if not ours.entries:
        return _("your mod list was empty — there was nothing of yours to carry over")
    if not theirs.entries:
        return _("the new upstream mod list is empty — refusing to merge onto nothing")
    if not base.entries:
        return _("the recorded upstream snapshot is empty — nothing to compare against")
    candidates = (
        (_("upstream snapshot"), base),
        (_("your list"), ours),
        (_("the new upstream list"), theirs),
    )
    for name, parsed in candidates:
        if parsed.has_duplicates:
            return _("{name} lists the same mod twice — refusing to guess").format(name=name)
        if parsed.stray:
            return _("{name} holds lines this tool does not understand: {line}").format(
                name=name, line=parsed.stray[0].strip()
            )
    return None


def _keep_first(names: Iterable[str]) -> list[str]:
    """Dédoublonne en gardant la première occurrence, l'ordre étant significatif."""
    return list(dict.fromkeys(names))


def _merge_states(
    order: list[str],
    base_by_name: dict[str, ListedEntry],
    ours_by_name: dict[str, ListedEntry],
    theirs: ParsedList,
) -> tuple[tuple[ListedEntry, ...], int, int]:
    """Attribue son marqueur à chaque nom retenu. Compte ce qui vient du joueur.

    Le marqueur entier est repris (pas seulement « activé/désactivé ») : `*`
    désigne un mod non géré par MO2, et le transformer en `+` changerait le
    sens de la ligne.
    """
    theirs_by_name = theirs.by_name
    entries: list[ListedEntry] = []
    reactivated = deactivated = 0
    for name in order:
        ours_entry = ours_by_name.get(name)
        theirs_entry = theirs_by_name.get(name)
        if ours_entry is None:
            assert theirs_entry is not None  # noqa: S101 - garanti par `allowed`
            entries.append(theirs_entry)
            continue
        if theirs_entry is None:
            entries.append(ours_entry)  # ajout du joueur, l'amont n'en sait rien
            continue
        base_entry = base_by_name.get(name)
        player_decided = base_entry is None or ours_entry.marker != base_entry.marker
        chosen = ours_entry if player_decided else theirs_entry
        entries.append(chosen)
        if player_decided and chosen.marker != theirs_entry.marker and not chosen.is_separator:
            if chosen.enabled:
                reactivated += 1
            else:
                deactivated += 1
    return tuple(entries), reactivated, deactivated


def _insert_near_neighbour(order: list[str], ours: list[str], name: str) -> None:
    """Replace `name` auprès de son voisin conservé le plus proche dans `ours`.

    On s'éloigne d'un cran à la fois, en regardant d'abord **au-dessus** (le
    voisin plus prioritaire) : ancrer sur lui et se poser juste en dessous
    reproduit « je l'avais mis sous celui-là ». Un ajout déjà replacé devient
    lui-même un ancrage, ce qui garde l'ordre relatif d'un groupe de mods
    ajoutés ensemble — le cas réel du haut de liste d'une install GAMMA.
    """
    placed = {existing: index for index, existing in enumerate(order)}
    origin = ours.index(name)
    for distance in range(1, len(ours)):
        above = origin - distance
        if above >= 0 and ours[above] in placed:
            order.insert(placed[ours[above]] + 1, name)
            return
        below = origin + distance
        if below < len(ours) and ours[below] in placed:
            order.insert(placed[ours[below]], name)
            return
    order.append(name)  # rien à quoi s'accrocher : la liste retenue est vide


def _alignment(base: list[str], other: list[str]) -> dict[int, int]:
    """Index de `base` → index correspondant dans `other`, pour les parties communes."""
    matcher = SequenceMatcher(a=base, b=other, autojunk=False)
    return {
        i + step: j + step for i, j, size in matcher.get_matching_blocks() for step in range(size)
    }


def _stable_runs(
    base: list[str], ours_map: dict[int, int], theirs_map: dict[int, int]
) -> list[tuple[int, int, int, int]]:
    """Plages de `base` alignées **des deux côtés** et contiguës : les points d'ancrage.

    Chaque plage est `(début base, fin base, début ours, début theirs)`. Ce qui
    tombe entre deux plages est une région modifiée d'au moins un côté, arbitrée
    par `_resolve_chunk`.
    """
    runs: list[tuple[int, int, int, int]] = []
    for index in range(len(base)):
        ours_index, theirs_index = ours_map.get(index), theirs_map.get(index)
        if ours_index is None or theirs_index is None:
            continue
        if runs:
            start, end, ours_start, theirs_start = runs[-1]
            offset = index - start
            if (
                index == end
                and ours_index == ours_start + offset
                and theirs_index == (theirs_start + offset)
            ):
                runs[-1] = (start, index + 1, ours_start, theirs_start)
                continue
        runs.append((index, index + 1, ours_index, theirs_index))
    return runs


def _resolve_chunk(
    chunk_base: list[str], chunk_ours: list[str], chunk_theirs: list[str]
) -> tuple[list[str], bool]:
    """Arbitre une région modifiée. Retourne (contenu retenu, conflit)."""
    if chunk_ours == chunk_base:
        return chunk_theirs, False  # seul l'amont a bougé
    if chunk_theirs == chunk_base:
        return chunk_ours, False  # seul le joueur a bougé
    if chunk_ours == chunk_theirs:
        return chunk_ours, False  # même changement des deux côtés
    return chunk_theirs, True  # les deux ont bougé : l'amont gagne, et on le dit


def _three_way_order(base: list[str], ours: list[str], theirs: list[str]) -> tuple[list[str], bool]:
    """diff3 sur la suite des noms. Retourne (suite fusionnée, y a-t-il eu conflit)."""
    runs = _stable_runs(base, _alignment(base, ours), _alignment(base, theirs))
    merged: list[str] = []
    conflicted = False
    base_cursor = ours_cursor = theirs_cursor = 0
    for start, end, ours_start, theirs_start in runs:
        chunk, has_conflict = _resolve_chunk(
            base[base_cursor:start],
            ours[ours_cursor:ours_start],
            theirs[theirs_cursor:theirs_start],
        )
        merged.extend(chunk)
        conflicted = conflicted or has_conflict
        merged.extend(base[start:end])
        length = end - start
        base_cursor, ours_cursor, theirs_cursor = end, ours_start + length, theirs_start + length
    chunk, has_conflict = _resolve_chunk(
        base[base_cursor:], ours[ours_cursor:], theirs[theirs_cursor:]
    )
    merged.extend(chunk)
    return merged, conflicted or has_conflict
