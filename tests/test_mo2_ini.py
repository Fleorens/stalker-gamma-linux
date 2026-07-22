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
