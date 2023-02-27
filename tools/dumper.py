import argparse
import os
from typing import Dict, List, Optional

from constants import *
from info_entry import RegionInt
from rom import Rom


TAB = "  "
RomDict = Dict[str, Dict[str, Rom]]


def check_flatten_int(num: Dict[str, int]) -> RegionInt:
    vals = list(num.values())
    if len(vals) == len(REGIONS) and all(v == vals[0] for v in vals):
        return vals[0]
    return num


def yaml_region_int(field: str, num: RegionInt) -> List[str]:
    if isinstance(num, int):
        return [f"{field}: 0x{num:X}"]
    return [f"{field}:"] + [f"{TAB}{k}: 0x{v:X}" for k, v in num.items()]


def yaml_data_entry(
    desc: str,
    label: str,
    type: str,
    addr: RegionInt,
    enum: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    lines = [
        f"desc: {desc}",
        f"label: {label}",
        f"type: {type}"
    ] + yaml_region_int("addr", addr)
    if enum is not None:
        lines.append(f"enum: 0x{enum}")
    if notes is not None:
        lines.append(f"notes: {notes}")
    return "-\n" + "\n".join(TAB + f for f in lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_dir", type=str)
    parser.add_argument("-g", "--game", type=str, choices=GAMES)
    parser.add_argument("-r", "--region", type=str, choices=REGIONS)
    args = parser.parse_args()

    # read rom files
    games = [args.game] if args.game else GAMES
    regions = [args.region] if args.region else REGIONS
    roms = {}
    for game in games:
        roms[game] = {}
        for region in regions:
            name = f"{game}_{region}.gba".lower()
            path = os.path.join(args.rom_dir, name)
            rom = Rom(path)
            roms[game][region] = rom
