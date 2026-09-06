"""Nature du support (`integrity/storage.py`) : `mountinfo` → `/dev/…` → `rotational`.

La suite ne peut pas fabriquer de vrai nœud de périphérique (il faut être root)
et ne peut pas non plus se fier au disque de la machine qui l'exécute. Les deux
chemins d'accès (`mountinfo`, `/sys/dev/block`) sont donc injectés, et le seul
périphérique réel utilisé est `/dev/null` — présent partout, y compris dans un
conteneur de CI, et suffisant pour que `stat` rende un `st_rdev` exploitable.
"""

from __future__ import annotations

import os
from pathlib import Path

from stalker_gamma_linux.integrity import storage

# `<id> <parent> <maj:min> <racine> <point de montage> <options> - <fs> <source> <superopts>`
_ROOT_LINE = "36 35 0:35 / / rw,relatime shared:1 - btrfs /dev/sdb5 rw,seclabel"
_GAMES_LINE = "70 36 0:52 / /mnt/jeux rw,noatime shared:130 - btrfs /dev/sda1 rw,seclabel"


def _mountinfo(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "mountinfo"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def _null_device_node() -> str:
    rdev = os.stat("/dev/null").st_rdev
    return f"{os.major(rdev)}:{os.minor(rdev)}"


class TestMountSource:
    def test_le_montage_le_plus_profond_gagne(self, tmp_path: Path) -> None:
        """Sinon `/` répondrait pour tout, et le disque de jeux ne serait jamais vu."""
        mountinfo = _mountinfo(tmp_path, _ROOT_LINE, _GAMES_LINE)

        mods = Path("/mnt/jeux/gamma/mods")

        assert storage.mount_source(mods, mountinfo=mountinfo) == "/dev/sda1"
        assert storage.mount_source(Path("/home/joueur"), mountinfo=mountinfo) == "/dev/sdb5"

    def test_prefixe_partiel_nest_pas_un_montage(self, tmp_path: Path) -> None:
        """`/mnt/jeux-old` n'est pas sous `/mnt/jeux`, malgré le préfixe de chaîne."""
        mountinfo = _mountinfo(tmp_path, _ROOT_LINE, _GAMES_LINE)

        assert storage.mount_source(Path("/mnt/jeux-old/mods"), mountinfo=mountinfo) == "/dev/sdb5"

    def test_dernier_montage_du_meme_point_masque_le_precedent(self, tmp_path: Path) -> None:
        later = "80 36 0:60 / /mnt/jeux rw shared:9 - ext4 /dev/nvme0n1p1 rw"
        mountinfo = _mountinfo(tmp_path, _ROOT_LINE, _GAMES_LINE, later)

        assert storage.mount_source(Path("/mnt/jeux"), mountinfo=mountinfo) == "/dev/nvme0n1p1"

    def test_espace_echappee_dans_le_point_de_montage(self, tmp_path: Path) -> None:
        r"""`mountinfo` écrit `\040` pour une espace : sans décodage, le montage est manqué."""
        escaped = r"71 36 0:53 / /mnt/Mes\040jeux rw shared:11 - btrfs /dev/sdc1 rw"
        mountinfo = _mountinfo(tmp_path, _ROOT_LINE, escaped)

        assert storage.mount_source(Path("/mnt/Mes jeux/mods"), mountinfo=mountinfo) == "/dev/sdc1"

    def test_lignes_malformees_ignorees_sans_lever(self, tmp_path: Path) -> None:
        mountinfo = _mountinfo(tmp_path, "n'importe quoi", "36 35 0:35 / /", _GAMES_LINE)

        assert storage.mount_source(Path("/mnt/jeux"), mountinfo=mountinfo) == "/dev/sda1"

    def test_fichier_absent_rend_none(self, tmp_path: Path) -> None:
        assert storage.mount_source(Path("/"), mountinfo=tmp_path / "nope") is None


class TestIsRotational:
    def _sysfs(self, tmp_path: Path, flag: str, *, as_partition: bool = False) -> Path:
        """Faux `/sys/dev/block` où `/dev/null` porte le drapeau `flag`."""
        sysfs = tmp_path / "sys"
        node = _null_device_node()
        if not as_partition:
            (sysfs / node / "queue").mkdir(parents=True)
            (sysfs / node / "queue" / "rotational").write_text(f"{flag}\n", encoding="ascii")
            return sysfs
        # Une partition : `queue/` vit sur le disque parent, atteint par `..`.
        (sysfs / "disque" / "queue").mkdir(parents=True)
        (sysfs / "disque" / "queue" / "rotational").write_text(f"{flag}\n", encoding="ascii")
        (sysfs / "disque" / "partition1").mkdir()
        (sysfs / node).symlink_to(sysfs / "disque" / "partition1")
        return sysfs

    def _mountinfo_on_null(self, tmp_path: Path) -> Path:
        return _mountinfo(tmp_path, "36 35 0:35 / /data rw shared:1 - btrfs /dev/null rw")

    def test_plateaux_detectes(self, tmp_path: Path) -> None:
        result = storage.is_rotational(
            Path("/data/gamma/mods"),
            mountinfo=self._mountinfo_on_null(tmp_path),
            sysfs_block=self._sysfs(tmp_path, "1"),
        )

        assert result is True

    def test_flash_detectee(self, tmp_path: Path) -> None:
        result = storage.is_rotational(
            Path("/data/gamma/mods"),
            mountinfo=self._mountinfo_on_null(tmp_path),
            sysfs_block=self._sysfs(tmp_path, "0"),
        )

        assert result is False

    def test_partition_retombe_sur_le_disque_parent(self, tmp_path: Path) -> None:
        """`/sys/dev/block/8:1/queue/` n'existe pas : le drapeau est sur `sda`, pas `sda1`."""
        result = storage.is_rotational(
            Path("/data"),
            mountinfo=self._mountinfo_on_null(tmp_path),
            sysfs_block=self._sysfs(tmp_path, "1", as_partition=True),
        )

        assert result is True

    def test_source_qui_nest_pas_un_bloc_rend_none(self, tmp_path: Path) -> None:
        """tmpfs, NFS, overlay : pas de disque derrière, donc pas de réponse."""
        mountinfo = _mountinfo(tmp_path, "36 35 0:50 / /data rw shared:1 - tmpfs tmpfs rw")

        result = storage.is_rotational(
            Path("/data"), mountinfo=mountinfo, sysfs_block=self._sysfs(tmp_path, "1")
        )

        assert result is None

    def test_sysfs_muet_rend_none_au_lieu_de_lever(self, tmp_path: Path) -> None:
        result = storage.is_rotational(
            Path("/data"),
            mountinfo=self._mountinfo_on_null(tmp_path),
            sysfs_block=tmp_path / "sys-absent",
        )

        assert result is None

    def test_sur_le_systeme_reel_repond_sans_lever(self, tmp_path: Path) -> None:
        """Contrat de robustesse : quelle que soit la machine, jamais d'exception."""
        assert storage.is_rotational(tmp_path) in (True, False, None)
