from stalker_gamma_linux.engine import markers

# Sorties réelles reprises des issues amont citées par T22
# (github.com/Mord3rca/gamma-launcher).

# Issue #286 : `anomaly-install`, ModDB refuse le lien (Cloudflare/403 constaté
# côté utilisateur, indiscernable d'un mirroir mort de notre point de vue).
_ISSUE_286 = (
    "Traceback (most recent call last):\n"
    '  File "/home/cheese/.venv/bin/gamma-launcher", line 6, in <module>\n'
    "    sys.exit(main())\n"
    '  File ".../launcher/mods/downloader/moddb.py", line 52, in _get_download_url\n'
    '    raise ModDBDownloadError(f"Download link not found when requesting {url}")\n'
    "launcher.exceptions.ModDBDownloadError: Download link not found when requesting "
    "https://www.moddb.com/downloads/start/277404"
)

# Issues #283/#284 : `full-install`, l'archive en cache pour « FDDA Redone
# Fixes » est en réalité une page d'erreur HTML (lien ModDB expiré) — py7zr
# plante sur `unpackinfo`, symptôme indirect et non la cause.
_ISSUE_283 = (
    "[+] Processing mod FDDA Redone Fixes (2/486)\n"
    "Calculating hash of FDDARD_FIX.7z: 100%|##########| 147/147\n"
    "Traceback (most recent call last):\n"
    '  File "launcher/mods/installer/base.py", line 36, in extract\n'
    "    self._dl.extract(to)\n"
    '  File "py7zr/py7zr.py", line 821, in _get_method_names\n'
    "AttributeError: 'NoneType' object has no attribute 'unpackinfo'\n"
    "[PYI-1739187:ERROR] Failed to execute script 'gamma-launcher' due to unhandled exception!"
)

# `check-md5` (verify) : archive locale absente/corrompue.
_HASH_FAILURE = "Hash verification failed for GAMMA_RC3.7z"

# Réseau injoignable après les trois tentatives internes de gamma-launcher
# (`tenacity`, `launcher/mods/downloader/base.py`).
_CONNECTION_ERROR = (
    "Traceback (most recent call last):\n"
    '  File "urllib3/connection.py", line 174, in _new_conn\n'
    "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='www.moddb.com', port=443): "
    "Max retries exceeded with url: /downloads/start/277404"
)


def test_classify_recognizes_moddb_link_not_found() -> None:
    assert markers.classify(_ISSUE_286) is markers.FailureCause.MOD_LINK_BROKEN


def test_classify_recognizes_unpackinfo_attribute_error_as_broken_link() -> None:
    # Le symptôme (py7zr) n'est pas confondu avec une vraie corruption locale :
    # c'est un lien ModDB expiré qui a livré une page d'erreur, pas une archive
    # abîmée après un téléchargement correct.
    assert markers.classify(_ISSUE_283) is markers.FailureCause.MOD_LINK_BROKEN


def test_classify_recognizes_local_corruption() -> None:
    assert markers.classify(_HASH_FAILURE) is markers.FailureCause.LOCAL_CORRUPTION


def test_classify_recognizes_network_unreachable() -> None:
    assert markers.classify(_CONNECTION_ERROR) is markers.FailureCause.NETWORK_UNREACHABLE


def test_classify_is_case_insensitive() -> None:
    cause = markers.classify("hash VERIFICATION failed for x")
    assert cause is markers.FailureCause.LOCAL_CORRUPTION


def test_classify_returns_none_for_unrelated_output() -> None:
    assert markers.classify("some completely unrelated crash") is None


def test_corruption_takes_priority_over_mod_link_broken_when_both_present() -> None:
    # Cas réel de `verify` (test_engine_runner.py) : une vraie corruption locale
    # ne doit jamais être masquée par une entrée invérifiable en ligne trouvée
    # dans la même sortie.
    combined = (
        "Could not find Filename in https://www.moddb.com/mods/x/addons/laser\n"
        "Hash verification failed for GAMMA_RC3.7z"
    )
    assert markers.classify(combined) is markers.FailureCause.LOCAL_CORRUPTION


def test_unverifiable_markers_is_the_mod_link_broken_table() -> None:
    # Contrat historique de `engine.runner.verify` : ne change pas de périmètre
    # avec la factorisation (pas de marqueurs réseau ajoutés sans le demander).
    assert markers.UNVERIFIABLE_MARKERS == markers.MOD_LINK_BROKEN_MARKERS
