import argparse

import argparse_utils as apu
from rom import Rom, ROM_OFFSET


def replace_ptrs(rom: Rom):
    start = rom.code_start()
    end = rom.data_end()
    rom_start = start + ROM_OFFSET
    rom_end = end + ROM_OFFSET
    data = bytearray(rom.data)
    for i in range(start, end, 4):
        val = rom.read32(i)
        if val >= rom_start and val < rom_end:
            # replace pointer with "find"
            data[i] = 0x66
            data[i + 1] = 0x69
            data[i + 2] = 0x6E
            data[i + 3] = 0x64
    rom.data = bytes(data)


class Finder(object):

    def __init__(self, src_rom: Rom, target_rom: Rom):
        replace_ptrs(src_rom)
        replace_ptrs(target_rom)
        self.src_rom = src_rom
        self.target_rom = target_rom

    def find(self, addr: int, t_start: int = None, t_end: int = None):
        s_end = self.src_rom.data_end()
        if t_start is None or t_end is None:
            if addr < self.src_rom.code_end():
                t_start = self.target_rom.code_start()
                t_end = self.target_rom.code_end()
            else:
                t_start = self.target_rom.data_start()
                t_end = self.target_rom.data_end()
        src = self.src_rom.data
        target = self.target_rom.data
        best_addr = -1
        best_size = -1
        for i in range(t_start, t_end):
            sa = addr
            ta = i
            while sa < s_end and ta < t_end and src[sa] == target[ta]:
                sa += 1
                ta += 1
            size = sa - addr
            if size > best_size:
                best_addr = i
                best_size = size
                if best_size > 0x10000:
                    break
        return best_addr, best_size


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
    for addr in addrs:
        ta, ts = finder.find(addr)
        print(f"{ta:X}\t{ts:X}")
