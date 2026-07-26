.PHONY: extract-messages update-messages compile-messages

LOCALE_DIR := src/stalker_gamma_linux/locale
POT_FILE := $(LOCALE_DIR)/stalker-gamma-linux.pot
LANGUAGES := fr

# i18n (see docs/ARCHITECTURE.md « Internationalisation »). Pure-Python tooling
# (Babel, `dev` extra) — no system `gettext`/`xgettext` package required.

# Regenerates the .pot template from every `_("...")` call in src/. Run after
# adding/changing any translatable string.
extract-messages:
	.venv/bin/pybabel extract -F babel.cfg -o $(POT_FILE) --no-location src/stalker_gamma_linux
	@echo "Template updated: $(POT_FILE)"

# Merges new/changed msgids from the .pot into each existing .po (keeps
# existing translations, marks new strings fuzzy/untranslated).
update-messages: extract-messages
	@for lang in $(LANGUAGES); do \
		.venv/bin/pybabel update -i $(POT_FILE) -d $(LOCALE_DIR) -l $$lang -D stalker-gamma-linux; \
	done

# Compiles every .po into the .mo gettext actually loads at runtime. Run
# before testing a translation locally or before a release.
compile-messages:
	.venv/bin/pybabel compile -d $(LOCALE_DIR) -D stalker-gamma-linux
	@echo "Compiled .mo files under $(LOCALE_DIR)/*/LC_MESSAGES/"
