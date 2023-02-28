import argparse
import sys
from typing import Dict, List, Tuple

from game_info import GameInfo
from info_entry import CodeEntry
from rom import Rom, ROM_OFFSET


class Finder(object):

    def __init__(self, src_rom: Rom, target_rom: Rom):
        self.convert_rom(src_rom)
        self.convert_rom(target_rom)
        self.src_rom = src_rom
        self.target_rom = target_rom

    def convert_rom(self, rom: Rom):
        start = rom.code_start()
        end = rom.data_end()
        rom_start = start + ROM_OFFSET
        rom_end = end + ROM_OFFSET
        data = bytearray(rom.data)
        for i in range(start, end, 4):
            orig = rom.read32(i)
            val = orig
            while val >= rom_start and val < rom_end:
                val = rom.read32(val - ROM_OFFSET)
            if val != orig:
                data[i] = val & 0xFF
                data[i + 1] = (val >> 8) & 0xFF
                data[i + 2] = (val >> 16) & 0xFF
                data[i + 3] = (val >> 24) & 0xFF
        rom.data = bytes(data)

    def find(self, addr: int):
        start = None
        end = None
        if addr < self.src_rom.code_end():
            start = self.target_rom.code_start()
            end = self.target_rom.code_end()
        else:
            start = self.target_rom.data_start()
            end = self.target_rom.data_end()
        src = self.src_rom.data
        target = self.target_rom.data
        best_addr = -1
        best_size = -1
        for i in range(start, end):
            size = 0
            while src[addr + size] == target[i + size]:
                size += 1
            if size > best_size:
                best_addr = i
                best_size = size
        return best_addr, best_size


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("src_rom_path", type=str)
    parser.add_argument("target_rom_path", type=str)
    parser.add_argument("addr", type=str)
    args = parser.parse_args()

    src_rom = Rom(args.src_rom_path)
    target_rom = Rom(args.target_rom_path)
    addr = int(args.addr, 16)

    finder = Finder(src_rom, target_rom)
    ta, ts = finder.find(addr)
    print(f"{ta:X}\t{ts:X}")
