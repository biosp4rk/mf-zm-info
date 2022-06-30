import argparse
from constants import *
import os
from typing import Dict, List, Optional
from rom import Rom


TAB = "  "
RomDict = Dict[str, Dict[str, Rom]]


def check_flatten_int(num: Dict[str, int]) -> VersionedInt:
    vals = list(num.values())
    if len(vals) == len(REGIONS) and all(v == vals[0] for v in vals):
        return vals[0]
    return num


def yaml_versioned_int(field: str, num: VersionedInt) -> List[str]:
    if isinstance(num, int):
        return [f"{field}: 0x{num:X}"]
    return [f"{field}:"] + [f"{TAB}{k}: 0x{v:X}" for k, v in num.items()]


def yaml_data_entry(
    desc: str,
    label: str,
    type: str,
    addr: VersionedInt,
    count: Optional[VersionedInt] = None,
    size: Optional[int] = None,
    enum: Optional[str] = None
) -> str:
    lines = [
        f"desc: {desc}",
        f"label: {label}",
        f"type: {type}"
    ] + yaml_versioned_int("addr", addr)
    if count is not None:
        lines += yaml_versioned_int("count", count)
    if size is not None:
        lines.append(f"size: 0x{size:X}")
    if enum is not None:
        lines.append(f"enum: 0x{enum}")
    return "-\n" + "\n".join(TAB + f for f in lines)


def find_oam(rom: Rom) -> None:
    entries = {}
    ptr_count = 0
    # (ptr dur)+ 00 00 00 00 00 00 00 00
    # DataStart <= ptr < DataEnd
    # 1 <= dur <= 0xFF
    data_addr = rom.data_start()
    data_end = rom.data_end()
    rom_data_start = rom.data_start(True)
    rom_data_end = rom.data_end(True)
    while data_addr < data_end:
        count = 0
        addr = data_addr
        while True:
            val = rom.read32(addr)
            # check if within data
            if val < rom_data_start or val >= rom_data_end:
                break
            val = rom.read32(addr + 4)
            if val < 1 or val > 0xFF:
                count = 0
                break
            count += 1
            addr += 8
        # check if oam found
        if count == 0:
            data_addr += 4
            continue
        # must end with eight 00 bytes
        if rom.read32(addr) == 0 and rom.read32(addr + 4) == 0:
            oam_label = f"OAM_{data_addr:X}"
            entries[data_addr] = yaml_data_entry(oam_label,
                oam_label, "Oam", {rom.region: data_addr}, count + 1)
            ptr_count += count
            for fn in range(count):
                fo = rom.read_ptr(data_addr + fn * 8)
                num_parts = rom.read16(fo)
                if num_parts >= 63:
                    continue
                frame_label = f"{oam_label}_Frame_{fn:02X}"
                entries[fo] = yaml_data_entry(frame_label, frame_label,
                    "oamframe", {rom.region: fo}, None, 2 + num_parts * 6)
            data_addr = addr + 8
        else:
            data_addr += 4
    # print(len(entries))
    # print(ptr_count)
    for k in sorted(entries):
        print(entries[k])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_dir", type=str)
    parser.add_argument("-g", "--game", type=str, choices=["mf", "zm"])
    parser.add_argument("-r", "--region", type=str, choices=["U", "E", "J"])
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
