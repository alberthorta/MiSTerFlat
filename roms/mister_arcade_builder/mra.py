"""Parse .mra files into the list of ROM files they need.

The rules follow Main_MiSTer support/arcade/mra_loader.cpp:
- tag and attribute names are case-insensitive;
- a zip name starting with "/" is relative to the games folder ("/hbmame/x.zip" is
  games/hbmame/x.zip); any other name is inside games/mame/;
- for each part, the zips in zip="a.zip|b.zip" are tried in order, and inside each zip
  the entry is found by CRC first and by name second;
- a <rom index="0"> may appear more than once (merged/split sets); once one of them
  loads with a valid md5, the next ones are skipped.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Set

HEX8 = re.compile(r"^[0-9a-f]{1,8}$")
BARE_AMP = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)")
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
TAG_NAME = re.compile(r"<(/?)([A-Za-z_][\w.-]*)")
XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>")


class MraParseError(Exception):
    pass


@dataclass(frozen=True)
class Part:
    zip: str        # zip we put the file in, as written in the .mra: the setname zip if listed, else the first
    name: str       # entry name inside the zip
    crc: str        # 8 lowercase hex digits
    optional: bool = False
    by_crc: bool = False  # name="none": MiSTer finds it by CRC only
    rom0_block: int = -1  # which <rom index="0"> it belongs to; -1 for other roms


@dataclass
class Mra:
    path: str
    name: str = ""
    setname: str = ""
    rbf: str = ""
    parts: List[Part] = field(default_factory=list)
    rom0_blocks: int = 0
    # every zip name listed in zip="a|b" attributes, lowercase, without folder
    zip_names: Set[str] = field(default_factory=set)

    @property
    def family(self) -> str:
        """The game this .mra belongs to: its _alternatives/_<game> folder, or its own title.

        The main .mra and its alternatives folder are spelled differently
        ("720 Degrees (rev 4).mra" vs "_720_Degrees"), so both are reduced to
        lowercase letters and digits, without the "(...)" suffix.
        """
        parts = self.path.split("/")
        if "_alternatives" in parts[:-1]:
            title = parts[parts.index("_alternatives") + 1]
        else:
            title = re.sub(r"\s*[(\[].*$", "", parts[-1][:-4])
        return re.sub(r"[^a-z0-9]", "", title.lower())


def norm_crc(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip().lower()
    if v.startswith("0x"):
        v = v[2:]
    if not v or not HEX8.match(v):
        return None
    return v.zfill(8)


def split_zips(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [z.strip() for z in value.split("|") if z.strip()]


def pick_zip(zips: List[str], setname: str) -> str:
    want = setname.lower() + ".zip"
    for z in zips:
        if z.rsplit("/", 1)[-1].lower() == want:
            return z
    return zips[0]


def zip_output_path(zip_name: str) -> str:
    """Path of the zip relative to the SD card root, as MiSTer looks for it."""
    if zip_name.startswith("/"):
        return "games" + zip_name
    return "games/mame/" + zip_name


def lower_names(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if isinstance(el.tag, str):
            el.tag = el.tag.lower()
        if any(k != k.lower() for k in el.attrib):
            el.attrib = {k.lower(): v for k, v in el.attrib.items()}
    return root


def parse_xml(data: bytes) -> ET.Element:
    try:
        return lower_names(ET.fromstring(data))
    except ET.ParseError as first:
        # MiSTer's own parser accepts things that strict XML does not: "--" inside
        # comments, a bare "&", and closing tags in a different case.
        text = data.decode("utf-8", errors="replace")
        text = XML_DECL.sub("", text)
        text = COMMENT.sub("", text)
        text = BARE_AMP.sub("&amp;", text)
        text = TAG_NAME.sub(lambda m: "<" + m.group(1) + m.group(2).lower(), text)
        try:
            return lower_names(ET.fromstring(text))
        except ET.ParseError:
            raise MraParseError(str(first)) from None


def parse_mra(path: str, data: bytes) -> Mra:
    root = parse_xml(data)
    if root.tag != "misterromdescription":
        raise MraParseError(f"unexpected root element <{root.tag}>")

    mra = Mra(
        path=path,
        name=(root.findtext("name") or "").strip(),
        setname=(root.findtext("setname") or "").strip(),
        rbf=(root.findtext("rbf") or "").strip(),
    )
    seen = set()
    for rom in root.iter("rom"):
        rom_zips = split_zips(rom.get("zip"))
        mra.zip_names.update(z.rsplit("/", 1)[-1].lower() for z in rom_zips)
        is_rom0 = (rom.get("index") or "0").strip() in ("0", "")
        block = -1
        if is_rom0 and rom_zips:
            block = mra.rom0_blocks
            mra.rom0_blocks += 1
        # interleave and group parts are nested; iter() walks the whole subtree.
        for part in rom.iter("part"):
            crc = norm_crc(part.get("crc"))
            if crc is None:
                continue  # inline bytes or filler: no file needed
            part_zips = split_zips(part.get("zip"))
            mra.zip_names.update(z.rsplit("/", 1)[-1].lower() for z in part_zips)
            zips = part_zips or rom_zips
            if not zips:
                continue
            name = (part.get("name") or "").strip()
            by_crc = not name or name.lower() == "none"
            if by_crc:
                name = f"{crc}.bin"
            zip_name = pick_zip(zips, mra.setname)
            key = (zip_name, name, crc, block)
            if key in seen:
                continue
            seen.add(key)
            mra.parts.append(Part(zip_name, name, crc, optional="ignore_crc" in part.attrib,
                                  by_crc=by_crc, rom0_block=block))
    return mra
