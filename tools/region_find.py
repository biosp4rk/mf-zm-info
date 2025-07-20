import argparse
from collections import defaultdict
from enum import Enum, auto

import argparse_utils as apu
from rom import Rom, ROM_OFFSET


ADDR_WINDOW = 0x18000
"""Range around the source data address to search in the target ROM."""
MAX_MATCH_SIZE = 0x1000
"""Max number of bytes to match (since checking more is wasteful)."""


class PtrReplacement(Enum):

    NONE = auto()
    """Don't replace any pointers."""
    COUNT = auto()
    """Replace pointers with the count of pointers before it."""
    VALUE = auto()
    """Replace pointers with the value they point to."""


def replace_ptrs_count(rom: Rom):
    start = rom.code_start()
    end = rom.data_end()
    rom_start = start + ROM_OFFSET
    rom_end = end + ROM_OFFSET
    data = bytearray(rom.data)
    ptr_count = 0
    for i in range(start, end, 4):
        val = rom.read_32(i)
        if val >= rom_start and val < rom_end:
            # Replace pointer with "ptr" and count
            data[i] = 0x70
            data[i + 1] = 0x74
            data[i + 2] = 0x72
            data[i + 3] = ptr_count & 0xFF
            ptr_count += 1
        else:
            ptr_count = 0
    rom.data = data


def replace_ptrs_value(rom: Rom):
    start = rom.code_start()
    end = rom.data_end()
    rom_start = start + ROM_OFFSET
    rom_end = end + ROM_OFFSET
    for i in range(start, end, 4):
        addr = i
        val = rom.read_32(i)
        while val >= rom_start and val < rom_end:
            addr = val - ROM_OFFSET
            val = rom.read_32(addr)
        if addr != i:
            rom.write_32(i, val)


class Finder(object):

    def __init__(self,
        src_rom: Rom,
        target_rom: Rom,
        ptr_replacement: PtrReplacement = PtrReplacement.COUNT
    ):
        if ptr_replacement == PtrReplacement.COUNT:
            replace_ptrs_count(src_rom)
            replace_ptrs_count(target_rom)
        elif ptr_replacement == PtrReplacement.VALUE:
            replace_ptrs_value(src_rom)
            replace_ptrs_value(target_rom)
        self.src_rom = src_rom
        self.target_rom = target_rom

    def find(self, addrs: list[int], t_start: int = None, t_end: int = None) -> list[tuple[int, int]]:
        # Get start and end address of target
        s_end = self.src_rom.data_end()
        if t_start is None:
            t_start = 0
        if t_end is None:
            t_end = len(self.target_rom.data) - 4
        # Get hash for each address
        addrs.sort()
        hashes: defaultdict[int, list[int]] = defaultdict(list)
        for addr in addrs:
            val = self.src_rom.read_32(addr)
            hashes[val].append(addr)
        # Search rom for matches
        src = self.src_rom.data
        target = self.target_rom.data
        best_matches = {addr: (-1, -1) for addr in addrs}
        for i in range(t_start, t_end):
            val = self.target_rom.read_32(i)
            if val not in hashes:
                continue
            hash_addrs = hashes[val]
            for addr in hash_addrs:
                if addr < i - ADDR_WINDOW:
                    continue
                if addr > i + ADDR_WINDOW:
                    break
                sa = addr
                ta = i
                while (
                    sa < s_end and ta < t_end and
                    src[sa] == target[ta] and
                    sa - addr < MAX_MATCH_SIZE
                ):
                    sa += 1
                    ta += 1
                size = sa - addr
                _, best_size = best_matches[addr]
                if size > best_size:
                    best_matches[addr] = (i, size)
        return [best_matches[addr] for addr in addrs]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH, "src_rom_path")
    apu.add_arg(parser, apu.ArgType.ROM_PATH, "target_rom_path")
    apu.add_arg(parser, apu.ArgType.ADDR_LIST)

    args = parser.parse_args()
    src_rom = apu.get_rom(args.src_rom_path)
    target_rom = apu.get_rom(args.target_rom_path)
    addrs = apu.get_hex_list(args.addr_list)

    finder = Finder(src_rom, target_rom)
    matches = finder.find(addrs)
    for ta, ts in matches:
        print(f"{ta:X}\t{ts:X}")
