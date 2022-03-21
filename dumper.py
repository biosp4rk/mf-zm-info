import argparse
from constants import *
import os
from typing import Dict, List, Optional, Union
from utils import load_yamls


SIZE_8MB = 0x800000
ROM_OFFSET = 0x80000000


class Rom(object):
    def __init__(self, path: str):
        # read file
        with open(path, "rb") as f:
            self.data = f.read()
        # check length
        if len(self.data) != SIZE_8MB:
            raise ValueError("ROM should be 8MB")
        # check title and code
        title = self.read_ascii(0xA0, 0x10)
        if title == "METROID4USA\0AMTE":
            self.game = GAME_MF
            self.region = REGION_U
        elif title == "METROID4EUR\0AMTP":
            self.game = GAME_MF
            self.region = REGION_E
        elif title == "METROID4JPN\0AMTJ":
            self.game = GAME_MF
            self.region = REGION_J
        elif title == "ZEROMISSIONEBMXE":
            self.game = GAME_ZM
            self.region = REGION_U
        elif title == "ZEROMISSIONPBMXP":
            self.game = GAME_ZM
            self.region = REGION_E
        elif title == "ZEROMISSIONJBMXJ":
            self.game = GAME_ZM
            self.region = REGION_J
        else:
            raise ValueError("Not a valid GBA Metroid ROM")

    def read8(self, addr: int) -> int:
        return self.data[addr]

    def read16(self, addr: int) -> int:
        return self.data[addr] | (self.data[addr + 1] << 8)

    def read32(self, addr: int) -> int:
        return (
            self.data[addr] |
            (self.data[addr + 1] << 8) |
            (self.data[addr + 2] << 16) |
            (self.data[addr + 3] << 24)
        )

    def read_ptr(self, addr: int) -> int:
        return (
            self.data[addr] |
            (self.data[addr + 1] << 8) |
            (self.data[addr + 2] << 16) |
            ((self.data[addr + 3] - 8) << 24)
        )

    def read_bytes(self, addr: int, size: int) -> bytes:
        end = addr + size
        return self.data[addr:end]

    def read_ascii(self, addr: int, size: int) -> str:
        return self.read_bytes(addr, size).decode("ascii")

    def code_start(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            addr = 0x230
        elif self.game == GAME_ZM:
            addr = 0x23C
        if virt:
            addr += ROM_OFFSET
        return addr

    def code_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            if self.region == REGION_U:
                addr = 0xA4FA4
            elif self.region == REGION_E:
                addr = 0xA5600
            elif self.region == REGION_J:
                addr = 0xA7290
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                addr = 0x8C71C
            elif self.region == REGION_E:
                addr = 0x8D3A8
            elif self.region == REGION_J:
                addr = 0x8C778
        if virt:
            addr += ROM_OFFSET
        return addr

    def data_start(self, virt: bool = False) -> int:
        return self.code_end(virt)
    
    def data_end(self, virt: bool = False) -> int:
        addr = None
        if self.game == GAME_MF:
            if self.region == REGION_U:
                addr = 0x79ECC8
            elif self.region == REGION_E:
                addr = 0x79F524
            elif self.region == REGION_J:
                addr = 0x7F145C
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                addr = 0x760D38
            elif self.region == REGION_E:
                addr = 0x775414
            elif self.region == REGION_J:
                addr = 0x760E48
        if virt:
            addr += ROM_OFFSET
        return addr

    def arm_functions(self) -> Dict[int, int]:
        if self.game == GAME_MF:
            if self.region == REGION_U:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_E:
                return {
                    0x3D78: 0x3E0C,
                    0x3E1C: 0x3EBC,
                    0x3ECC: 0x4514,
                    0x4518: 0x4530,
                    0x4534: 0x45A8
                }
            elif self.region == REGION_J:
                return {
                    0x3DDC: 0x3E70,
                    0x3E80: 0x3F20,
                    0x3F30: 0x4578,
                    0x457C: 0x4594,
                    0x4598: 0x460C
                }
        elif self.game == GAME_ZM:
            if self.region == REGION_U:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }
            elif self.region == REGION_E:
                return {
                    0x4374: 0x4408,
                    0x4418: 0x44B8,
                    0x44C8: 0x4B10,
                    0x4B14: 0x4B2C,
                    0x4B30: 0x4BA4
                }
            elif self.region == REGION_J:
                return {
                    0x4320: 0x43B4,
                    0x43C4: 0x4464,
                    0x4474: 0x4ABC,
                    0x4AC0: 0x4AD8,
                    0x4ADC: 0x4B50
                }

    def find_bytes(self, pat: bytes, start: int = 0) -> int:
        return self.data.find(pat, start)


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
