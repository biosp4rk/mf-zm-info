import argparse

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
            val = rom.read32(i)
            if val >= rom_start and val < rom_end:
                # replace pointer with "find"
                data[i] = 0x66
                data[i + 1] = 0x69
                data[i + 2] = 0x6E
                data[i + 3] = 0x64
        rom.data = bytes(data)

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
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    parser.add_argument("src_rom_path", type=str)
    parser.add_argument("target_rom_path", type=str)
    apu.add_addr_arg(parser)

    args = parser.parse_args()
    src_rom = Rom(args.src_rom_path)
    target_rom = Rom(args.target_rom_path)
    addr = apu.get_rom(args)

    finder = Finder(src_rom, target_rom)
    ta, ts = finder.find(addr)
    print(f"{ta:X}\t{ts:X}")
