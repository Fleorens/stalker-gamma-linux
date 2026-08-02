"""Sélection de langue (`i18n`) — anglais par défaut, `LANGUAGE` seul décide.

Comportement délibéré et contre-intuitif : contrairement à `gettext` standard,
on **ne suit pas** la locale système. Un poste en `fr_FR.UTF-8` doit afficher
l'anglais tant que l'utilisateur n'a pas demandé autre chose explicitement
(commit 90139b7). Rien ne le vérifiait : un retour au comportement par défaut
de `gettext.translation` serait passé inaperçu jusqu'à ce qu'un utilisateur
signale une CLI soudain en français.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest

from stalker_gamma_linux import i18n

_LOCALE_VARS = ("LANGUAGE", "LANG", "LC_ALL", "LC_MESSAGES")

# Traduction française existante, choisie courte et stable (voir le .po).
_TRANSLATED_MSGID = "Error"
_TRANSLATED_FR = "Erreur"


@pytest.fixture
def reload_i18n(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    """Recharge `i18n` avec un environnement donné, puis restaure l'état initial.

    `_translation` est résolu à l'import : changer les variables d'environnement
    après coup n'a aucun effet, il faut donc recharger le module. Le rechargement
    final évite de laisser une traduction exotique aux autres tests.
    """

    def _reload(**env: str) -> object:
        for var in _LOCALE_VARS:
            monkeypatch.delenv(var, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(i18n)

    yield _reload
    monkeypatch.undo()
    importlib.reload(i18n)


class TestRequestedLanguages:
    def test_sans_language_langlais_est_demande(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        module = reload_i18n()

        assert module._requested_languages() == ["en"]

    def test_la_locale_systeme_est_ignoree(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        """Le cœur du comportement : `LANG`/`LC_ALL` ne doivent rien changer."""
        module = reload_i18n(LANG="fr_FR.UTF-8", LC_ALL="fr_FR.UTF-8", LC_MESSAGES="fr_FR.UTF-8")

        assert module._requested_languages() == ["en"]

    def test_language_explicite_est_suivi(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        module = reload_i18n(LANGUAGE="fr")

        assert module._requested_languages() == ["fr"]

    def test_language_accepte_une_liste_de_repli(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        module = reload_i18n(LANGUAGE="de:fr:en")

        assert module._requested_languages() == ["de", "fr", "en"]


class TestTraductionEffective:
    def test_locale_fr_seule_rend_quand_meme_langlais(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        """Bout en bout : c'est ce que voit l'utilisateur sur un poste français."""
        module = reload_i18n(LANG="fr_FR.UTF-8", LC_ALL="fr_FR.UTF-8")

        assert module._(_TRANSLATED_MSGID) == _TRANSLATED_MSGID

    def test_language_fr_rend_le_francais(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        module = reload_i18n(LANGUAGE="fr")

        assert module._(_TRANSLATED_MSGID) == _TRANSLATED_FR

    def test_langue_inconnue_retombe_sur_le_msgid(self, reload_i18n) -> None:  # type: ignore[no-untyped-def]
        """Pas de `.mo` pour cette langue : `NullTranslations`, donc le texte source."""
        module = reload_i18n(LANGUAGE="xx_YY")

        assert module._(_TRANSLATED_MSGID) == _TRANSLATED_MSGID
