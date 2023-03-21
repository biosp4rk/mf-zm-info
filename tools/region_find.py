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


class SeqAlign(object):
    def __init__(self, rom1: Rom, rom2: Rom):
        self.rom1 = rom1
        self.rom2 = rom2

    def align(self,
        rom1_start: int,
        rom1_end: int,
        rom2_start: int,
        rom2_end: int
    ):
        # check sizes
        m = rom1_end - rom1_start
        n = rom2_end - rom2_start
        if m * n > 100_000_000:
            print(f"{m} x {n} ({m * n}) is too big")
            return

        # create matrix of distances
        d = [[0 for _ in range(n+1)] for _ in range(m+1)]

        # fill distances for source prefixes
        for i in range(1, m+1):
            d[i][0] = i
        # fill distances for target prefixes
        for j in range(1, n+1):
            d[0][j] = j
        
        # fill in remainder of matrix
        for j in range(1, n+1):
            b2 = self.rom2.data[rom2_start + j - 1]
            for i in range(1, m+1):
                b1 = self.rom1.data[rom1_start + i - 1]
                sub_cost = 0 if b1 == b2 else 1
                d[i][j] = min(
                    d[i-1][j] + 1, # deletion
                    d[i][j-1] + 1, # insertion
                    d[i-1][j-1] + sub_cost, # substitution
                )
        # get path taken
        i = m
        j = n
        path = []
        while i > 0 or j > 0:
            # get costs
            del_cost = 0x2000000
            ins_cost = 0x2000000
            sub_cost = 0x2000000
            if i > 0:
                del_cost = d[i-1][j]
            if j > 0:
                ins_cost = d[i][j-1]
            if i > 0 and j > 0:
                sub_cost = d[i-1][j-1]
            # find best
            if del_cost < ins_cost and del_cost < sub_cost:
                path.append((i, j, "DEL"))
                i -= 1
            elif ins_cost < sub_cost:
                path.append((i, j, "INS"))
                j -= 1
            else:
                if d[i-1][j-1] < d[i][j]:
                    path.append((i, j, "SUB"))
                i -= 1
                j -= 1
        # get addresses and values involved
        details = []
        for i, j, act in reversed(path):
            s = None
            addr1 = rom1_start + i - 1
            if act == "DEL":
                b = self.rom1.data[addr1]
                s = f"DEL {b:02X}"
            elif act == "INS":
                b = self.rom2.data[rom2_start + j - 1]
                s = f"INS {b:02X}"
            elif act == "SUB":
                b1 = self.rom1.data[addr1]
                b2 = self.rom2.data[rom2_start + j - 1]
                s = f"SUB {b1:02X} -> {b2:02X}"
            details.append(f"{addr1:X}: {s}")
        return details


if __name__ == "__main__":
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    parser.add_argument("src_rom_path", type=str)
    parser.add_argument("target_rom_path", type=str)
    apu.add_addrs_arg(parser)

    args = parser.parse_args()
    src_rom = Rom(args.src_rom_path)
    target_rom = Rom(args.target_rom_path)
    addrs = apu.get_addrs(args)

    finder = Finder(src_rom, target_rom)
    for addr in addrs:
        ta, ts = finder.find(addr)
        print(f"{ta:X}\t{ts:X}")
