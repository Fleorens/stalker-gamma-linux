# Packaging entry points (T09). See docs/PACKAGING.md for what each channel
# bundles, why, and how to test it. Each target builds locally — no network
# egress except to fetch pinned upstream sources.

.PHONY: package-flatpak package-flatpak-bundle package-appimage package-flathub-stage clean-packaging

package-flatpak:
	cd packaging/flatpak && \
	flatpak-builder --user --force-clean --repo=.flatpak-repo build-dir \
		org.stalkergammalinux.Gui.yml
	@echo
	@echo "Install locally with:"
	@echo "  flatpak --user remote-add --if-not-exists --no-gpg-verify local-repo packaging/flatpak/.flatpak-repo"
	@echo "  flatpak --user install --reinstall -y local-repo org.stalkergammalinux.Gui"

# Bundle unique installable (`flatpak install ./*.flatpak`) pour les artefacts
# de release (T10) — le `.flatpak-repo` produit par `package-flatpak` ci-dessus
# ne contient que notre appli, jamais le runtime GNOME : `--runtime-repo`
# référence Flathub pour que l'installateur sache où le récupérer.
package-flatpak-bundle: package-flatpak
	mkdir -p packaging/flatpak/dist
	flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
		packaging/flatpak/.flatpak-repo \
		packaging/flatpak/dist/org.stalkergammalinux.Gui.flatpak \
		org.stalkergammalinux.Gui

package-appimage:
	packaging/appimage/build.sh

package-flathub-stage:
	packaging/flatpak/flathub/collect.sh

clean-packaging:
	rm -rf packaging/flatpak/.flatpak-builder packaging/flatpak/build-dir \
		packaging/flatpak/.flatpak-repo packaging/flatpak/dist
	rm -rf packaging/appimage/.build packaging/appimage/dist \
		packaging/appimage/.tool-venv
	rm -rf packaging/flatpak/flathub/org.stalkergammalinux.Gui
