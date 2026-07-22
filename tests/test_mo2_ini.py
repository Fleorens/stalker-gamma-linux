from stalker_gamma_linux.mo2 import ini

_SAMPLE = (
    "[General]\n"
    "gameName=STALKER Anomaly\n"
    "version=2.5.2\n"
    "\n"
    "[customExecutables]\n"
    "size=1\n"
    "1\\title=Anomaly (DX11)\n"
)


def test_read_key_scoped_to_section() -> None:
    assert ini.read_key(_SAMPLE, "General", "gameName") == "STALKER Anomaly"
    assert ini.read_key(_SAMPLE, "customExecutables", "size") == "1"
    # `size` n'existe pas dans [General] : la recherche est bien bornée à la section.
    assert ini.read_key(_SAMPLE, "General", "size") is None


def test_read_key_absent_section_returns_none() -> None:
    assert ini.read_key(_SAMPLE, "Nope", "gameName") is None


def test_set_key_replaces_existing_value_in_place() -> None:
    result = ini.set_key(_SAMPLE, "General", "version", "2.5.3")

    assert ini.read_key(result, "General", "version") == "2.5.3"
    # Aucune ligne ajoutée, le reste est intact.
    assert result.count("version=") == 1
    assert "[customExecutables]" in result
    assert "1\\title=Anomaly (DX11)" in result


def test_set_key_inserts_missing_key_into_section() -> None:
    result = ini.set_key(_SAMPLE, "General", "first_start", "false")

    assert ini.read_key(result, "General", "first_start") == "false"
    # Insérée dans [General], pas dans [customExecutables].
    assert ini.read_key(result, "customExecutables", "first_start") is None


def test_set_key_creates_missing_section() -> None:
    result = ini.set_key(_SAMPLE, "Settings", "foo", "bar")

    assert "[Settings]" in result
    assert ini.read_key(result, "Settings", "foo") == "bar"


def test_set_key_on_empty_text_creates_section_and_key() -> None:
    result = ini.set_key("", "General", "gameName", "X")

    assert result == "[General]\ngameName=X\n"


def test_bytearray_roundtrip_escapes_backslashes() -> None:
    result = ini.set_bytearray_key("", "General", "gamePath", r"Z:\home\x\anomaly")

    # Dans le fichier, les backslashes sont doublés (échappement Qt).
    assert r"gamePath=@ByteArray(Z:\\home\\x\\anomaly)" in result
    # Relu, on récupère le chemin d'origine.
    assert ini.read_bytearray_key(result, "General", "gamePath") == r"Z:\home\x\anomaly"


def test_read_bytearray_key_on_unwrapped_value_returns_raw() -> None:
    text = "[General]\nselected_profile=Default\n"

    assert ini.read_bytearray_key(text, "General", "selected_profile") == "Default"


def test_editing_preserves_unrelated_bytearray_blobs() -> None:
    text = "[General]\nwindow_geometry=@ByteArray(\\x1\\x2\\0abc)\ngameName=X\n"

    result = ini.set_bytearray_key(text, "General", "gamePath", r"Z:\g")

    # Le blob opaque n'est pas touché.
    assert "window_geometry=@ByteArray(\\x1\\x2\\0abc)" in result
    assert ini.read_bytearray_key(result, "General", "gamePath") == r"Z:\g"


def test_set_key_preserves_trailing_newline_state() -> None:
    with_newline = "[General]\na=1\n"
    without_newline = "[General]\na=1"

    assert ini.set_key(with_newline, "General", "a", "2").endswith("\n")
    assert not ini.set_key(without_newline, "General", "a", "2").endswith("\n")


# Extrait réel d'une instance GAMMA : les exécutables sont des customExecutables
# aux chemins absolus, en slashs avant (binary/workingDirectory) et backslashes
# doublés (arguments).
_REAL_EXECS = (
    "[customExecutables]\n"
    "size=2\n"
    "3\\binary=Z:/old/GAMMA/gamma/anomaly/bin/AnomalyDX11.exe\n"
    "3\\title=Anomaly (DX11)\n"
    "3\\workingDirectory=Z:/old/GAMMA/gamma/anomaly/bin\n"
    "1\\binary=Z:/old/GAMMA/gamma/anomaly/AnomalyLauncher.exe\n"
    "1\\workingDirectory=Z:/old/GAMMA/gamma/anomaly\n"
    "10\\binary=Z:/old/GAMMA/gamma/gamma/explorer++/Explorer++.exe\n"
    '10\\arguments=\\"Z:\\\\old\\\\GAMMA\\\\gamma\\\\anomaly\\"\n'
)


def test_rebase_rewrites_forward_slash_executable_paths() -> None:
    result = ini.rebase_windows_path(
        _REAL_EXECS, r"Z:\old\GAMMA\gamma\anomaly", r"Z:\new\anomaly"
    )

    assert "3\\binary=Z:/new/anomaly/bin/AnomalyDX11.exe" in result
    assert "3\\workingDirectory=Z:/new/anomaly/bin" in result
    assert "1\\binary=Z:/new/anomaly/AnomalyLauncher.exe" in result
    # Frontière de fin de valeur : le workingDirectory du launcher == la racine.
    assert "1\\workingDirectory=Z:/new/anomaly\n" in result


def test_rebase_rewrites_escaped_backslash_arguments() -> None:
    result = ini.rebase_windows_path(
        _REAL_EXECS, r"Z:\old\GAMMA\gamma\anomaly", r"Z:\new\anomaly"
    )

    assert '10\\arguments=\\"Z:\\\\new\\\\anomaly\\"' in result


def test_rebase_leaves_sibling_paths_untouched() -> None:
    # explorer++ vit sous .../gamma/gamma, PAS sous .../gamma/anomaly : intact.
    result = ini.rebase_windows_path(
        _REAL_EXECS, r"Z:\old\GAMMA\gamma\anomaly", r"Z:\new\anomaly"
    )

    assert "10\\binary=Z:/old/GAMMA/gamma/gamma/explorer++/Explorer++.exe" in result


def test_rebase_is_noop_when_roots_equal_or_empty() -> None:
    assert ini.rebase_windows_path(_REAL_EXECS, r"Z:\a", r"Z:\a") == _REAL_EXECS
    assert ini.rebase_windows_path(_REAL_EXECS, "", r"Z:\a") == _REAL_EXECS


def test_rebase_respects_segment_boundary() -> None:
    text = "a=Z:/games/anomaly_backup/x\nb=Z:/games/anomaly/x\n"

    result = ini.rebase_windows_path(text, r"Z:\games\anomaly", r"Z:\new")

    # `anomaly` ne doit pas matcher dans `anomaly_backup`.
    assert "a=Z:/games/anomaly_backup/x" in result
    assert "b=Z:/new/x" in result
