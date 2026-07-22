"""Édition chirurgicale du `ModOrganizer.ini` (format Qt `QSettings`).

On **ne réécrit jamais tout le fichier** : MO2 y sérialise des valeurs Qt
opaques (`window_geometry`, blobs `@ByteArray(...)`, sections `[customExecutables]`
indexées) qu'un `configparser` classique corromprait. On remplace donc, ligne à
ligne, uniquement les clés qu'on maîtrise (`gamePath`, `selected_profile`…) en
préservant tout le reste octet pour octet.

Toutes les fonctions sont pures : elles reçoivent le texte du fichier et
retournent un **nouveau** texte (immutabilité), sans effet de bord.
"""

from __future__ import annotations

import re

_SECTION_RE = re.compile(r"^\[(?P<name>.*)\]\s*$")
_BYTEARRAY_RE = re.compile(r"^@ByteArray\((?P<inner>.*)\)$", re.DOTALL)


def _find_section_body(lines: list[str], section: str) -> tuple[int, int] | None:
    """Retourne `(header_index, end_index)` de la section, ou None si absente.

    Le corps de la section est `lines[header_index + 1 : end_index]` ; `end_index`
    est l'indice de l'en-tête de section suivant, ou `len(lines)`.
    """
    header = None
    for idx, line in enumerate(lines):
        match = _SECTION_RE.match(line)
        if match is not None and match.group("name") == section:
            header = idx
            break
    if header is None:
        return None
    end = len(lines)
    for idx in range(header + 1, len(lines)):
        if _SECTION_RE.match(lines[idx]) is not None:
            end = idx
            break
    return header, end


def read_key(text: str, section: str, key: str) -> str | None:
    """Valeur brute (telle qu'écrite après `=`) de `key` dans `section`, ou None."""
    lines = text.splitlines()
    body = _find_section_body(lines, section)
    if body is None:
        return None
    header, end = body
    key_re = re.compile(rf"^{re.escape(key)}=(.*)$")
    for idx in range(header + 1, end):
        match = key_re.match(lines[idx])
        if match is not None:
            return match.group(1)
    return None


def set_key(text: str, section: str, key: str, raw_value: str) -> str:
    """Nouveau texte où `key` vaut `raw_value` dans `section` (créées au besoin).

    La valeur est écrite verbatim après `=` (l'appelant a déjà encodé ce qu'il
    fallait, cf. `set_bytearray_key`). L'ordre des clés dans une section INI
    n'ayant pas de sens, une clé absente est insérée juste après l'en-tête.
    """
    lines = text.splitlines()
    new_line = f"{key}={raw_value}"
    body = _find_section_body(lines, section)
    if body is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        lines.append(new_line)
    else:
        header, end = body
        key_re = re.compile(rf"^{re.escape(key)}=")
        replaced = False
        for idx in range(header + 1, end):
            if key_re.match(lines[idx]) is not None:
                lines[idx] = new_line
                replaced = True
                break
        if not replaced:
            lines.insert(header + 1, new_line)
    result = "\n".join(lines)
    if not text or text.endswith("\n"):
        result += "\n"
    return result


def escape_bytearray(value: str) -> str:
    """Échappe une valeur pour le contenu d'un `@ByteArray(...)` (Qt double les `\\`)."""
    return value.replace("\\", "\\\\")


def unescape_bytearray(inner: str) -> str:
    return inner.replace("\\\\", "\\")


def wrap_bytearray(value: str) -> str:
    return f"@ByteArray({escape_bytearray(value)})"


def read_bytearray_key(text: str, section: str, key: str) -> str | None:
    """Valeur d'une clé `@ByteArray(...)`, désenveloppée et déséchappée.

    Si la clé existe mais n'est pas enveloppée dans `@ByteArray(...)` (variante
    plus ancienne de MO2), la valeur brute est renvoyée telle quelle.
    """
    raw = read_key(text, section, key)
    if raw is None:
        return None
    match = _BYTEARRAY_RE.match(raw)
    if match is None:
        return raw
    return unescape_bytearray(match.group("inner"))


def set_bytearray_key(text: str, section: str, key: str, value: str) -> str:
    """Écrit `key=@ByteArray(<value échappée>)` dans `section` (format MO2 des chemins)."""
    return set_key(text, section, key, wrap_bytearray(value))


def rebase_windows_path(text: str, old_root: str, new_root: str) -> str:
    r"""Réécrit un préfixe de chemin Windows partout dans le texte, aux **deux**
    conventions présentes dans `ModOrganizer.ini` :

    - slashs avant (`Z:/a/b`) — clés `binary`/`workingDirectory` de
      `[customExecutables]` ;
    - backslashes doublés (`Z:\\a\\b`) — valeurs `@ByteArray(...)` et
      `arguments`.

    Le remplacement n'a lieu qu'aux **frontières de segment** (fin de valeur, `/`,
    `\`, `"`) pour ne pas toucher un dossier voisin (`anomaly` dans `anomaly_old`).
    `old_root`/`new_root` sont donnés en forme canonique à backslashes simples
    (comme `to_windows_path`). No-op si `old_root` est vide ou égal à `new_root`.
    """
    if not old_root or old_root == new_root:
        return text
    old_fwd, new_fwd = old_root.replace("\\", "/"), new_root.replace("\\", "/")
    old_esc, new_esc = old_root.replace("\\", "\\\\"), new_root.replace("\\", "\\\\")
    # Lambdas en remplacement : évite l'interprétation des backslashes par re.sub.
    text = re.sub(re.escape(old_fwd) + r'(?=/|"|$)', lambda _: new_fwd, text, flags=re.MULTILINE)
    text = re.sub(re.escape(old_esc) + r'(?=\\|"|$)', lambda _: new_esc, text, flags=re.MULTILINE)
    return text
