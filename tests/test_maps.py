import struct
from pathlib import Path

from mordhau_panel.maps import MapCatalog, group_by_mode, umap_names_in_pak

MAGIC = struct.pack("<I", 0x5A6F12E1)


def fstring(text: str) -> bytes:
    data = text.encode() + b"\x00"
    return struct.pack("<i", len(data)) + data


def footer(version: int, index_offset: int, index_size: int) -> bytes:
    return (
        b"\x00" * 16  # encryption key guid
        + b"\x00"  # index not encrypted
        + MAGIC
        + struct.pack("<IQQ", version, index_offset, index_size)
        + b"\x00" * 20  # index hash
        + b"\x00" * 32 * 5  # compression method names
    )


def write_v11_pak(path: Path, directories: dict[str, list[str]]) -> None:
    """Pak v10+ layout: filenames live in the full directory index."""
    body = b"\xab" * 64  # stand-in for file data
    directory_index = struct.pack("<i", len(directories))
    for dir_name, files in directories.items():
        directory_index += fstring(dir_name) + struct.pack("<i", len(files))
        for name in files:
            directory_index += fstring(name) + struct.pack("<i", 0)
    dir_offset = len(body)
    primary = (
        fstring("../../../Mordhau/Content/")
        + struct.pack("<iQ", sum(len(f) for f in directories.values()), 0)
        + struct.pack("<I", 1) + struct.pack("<qq", 0, 0) + b"\x00" * 20  # path hash index
        + struct.pack("<I", 1) + struct.pack("<qq", dir_offset, len(directory_index)) + b"\x00" * 20
    )
    index_offset = dir_offset + len(directory_index)
    path.write_bytes(body + directory_index + primary + footer(11, index_offset, len(primary)))


def write_legacy_pak(path: Path, files: list[str]) -> None:
    """Pre-v10 layout: filenames are inline in the primary index."""
    body = b"\xcd" * 32
    index = fstring("../../../") + struct.pack("<i", len(files))
    for name in files:
        index += fstring(name) + b"\x00" * 53  # entry record
    path.write_bytes(body + index + footer(8, len(body), len(index)))


def test_reads_v11_directory_index(tmp_path):
    pak = tmp_path / "pakchunk0-LinuxServer.pak"
    write_v11_pak(pak, {
        "Mordhau/Maps/DuelCamp/": ["FFA_Camp.umap", "Camp_Interactables.umap", "Camp.uexp"],
        "Mordhau/Maps/Grad/": ["TDM_Grad.umap"],
    })
    assert umap_names_in_pak(pak) == {"FFA_Camp", "Camp_Interactables", "TDM_Grad"}


def test_reads_legacy_inline_index(tmp_path):
    pak = tmp_path / "old.pak"
    write_legacy_pak(pak, ["Mordhau/Content/Maps/SKM_Taiga.umap", "Mordhau/Content/Maps/Taiga.uasset"])
    assert umap_names_in_pak(pak) == {"SKM_Taiga"}


def test_groups_playable_maps_by_mode():
    names = {"FFA_Camp", "TDM_Camp", "FFA_ThePit", "Camp", "Grad_Brawl", "SC_CampTutorial", "MainMenu", "TF_Arena"}
    assert group_by_mode(names) == [
        {"prefix": "FFA", "label": "Free-for-all", "maps": ["FFA_Camp", "FFA_ThePit"]},
        {"prefix": "TDM", "label": "Team deathmatch", "maps": ["TDM_Camp"]},
        {"prefix": "TF", "label": "TF", "maps": ["TF_Arena"]},
    ]


def test_catalog_skips_broken_paks_and_refreshes_on_change(tmp_path):
    write_v11_pak(tmp_path / "a.pak", {"Maps/": ["FFA_Camp.umap"]})
    (tmp_path / "broken.pak").write_bytes(b"not a pak")
    catalog = MapCatalog(tmp_path)
    assert catalog.names() == {"FFA_Camp"}
    assert len(catalog.errors) == 1

    write_v11_pak(tmp_path / "b.pak", {"Maps/": ["SKM_Grad.umap"]})
    assert catalog.names() == {"FFA_Camp", "SKM_Grad"}


def test_catalog_without_server_files(tmp_path):
    assert MapCatalog(tmp_path / "missing").modes() == []
