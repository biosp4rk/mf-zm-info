import argparse
from constants import *
import os
from typing import Dict, List, Optional, Union
from rom import Rom
from utils import load_yamls


TAB = "  "
RomDict = Dict[str, Dict[str, Rom]]
VersionedInt = Union[int, Dict[str, int]]


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



def dump_room_sprites(roms: RomDict) -> None:
    RE = "RoomEntry"
    RSE = "RoomSpriteEntry"
    pRSE = f"ptr.{RSE}"
    END = bytes([0xFF, 0xFF, 0xFF])
    for game, game_roms in roms.items():
        # get room entry struct
        structs = load_yamls(game, MAP_STRUCTS)
        room_struct = structs[RE]
        room_struct_size = room_struct["size"]
        layout_ptrs = [
            v["offset"]
            for v in room_struct["vars"]
            if v["type"] == pRSE
        ]
        # get room entries in rom data
        data = load_yamls(game, MAP_DATA)
        data = [d for d in data if d.get("type") == RE]
        # go through each area
        layouts = []
        for area in data:
            area_addr = area["addr"]
            area_name = area["label"]
            assert area_name.endswith("RoomEntries")
            area_name = area_name.replace("RoomEntries", "")
            room_count = area["count"]
            # go through each room
            for room in range(room_count):
                off = room * room_struct_size
                room_addr = {k: v + off for k, v in area_addr.items()}
                # go through each sprite layout
                for i, off in enumerate(layout_ptrs):
                    layout_addr = {
                        k: game_roms[k].read_ptr(v + off)
                        for k, v in room_addr.items()
                    }
                    layout_size = {
                        k: (game_roms[k].find_bytes(END, v) - v)
                        for k, v in layout_addr.items()
                    }
                    layout_count = {
                        k: 1 + (v // 3)
                        for k, v in layout_size.items()
                    }
                    layout_count = check_flatten_int(layout_count)
                    label = f"{area_name}_{room:02X}_SpriteLayout{i}"
                    layouts.append((label, layout_addr, layout_count))
        layouts.sort(key=lambda x: x[1]["U"])
        for entry in layouts:
            label, addr, count = entry
            y = yaml_data_entry(label, label, RSE, addr, count)
            print(y)


def dump_pcm(roms: RomDict) -> None:
    addrs = []

    mf_u = roms[GAME_MF][REGION_U]
    mf_e = roms[GAME_MF][REGION_E]
    mf_j = roms[GAME_MF][REGION_J]

    for addr in addrs:
        size = mf_u.read32(addr + 0xC) + 0x10
        desc = f"PCM sample {addr:X}"
        label = f"pcm_{addr:X}"
        # find in E and J
        pat = mf_u.read_bytes(addr, size)
        addr_e = mf_e.find_bytes(pat)
        addr_j = mf_j.find_bytes(pat)
        ad = {"U": addr, "E": addr_e, "J": addr_j}
        y = yaml_data_entry(desc, label, "PcmSample", ad, None, size)
        print(y)


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

    dump_room_sprites(roms)
