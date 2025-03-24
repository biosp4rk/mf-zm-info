import argparse
from collections import defaultdict
import re

import argparse_utils as apu
from function import all_functions
from game_info import GameInfo, InfoSource
from info_entry import VarEntry
from rom import Rom, ROM_OFFSET


def dump_bytes(
    rom: Rom,
    addr: int,
    length: int,
    size: int = 1,
    per_line: int = None
):
    assert size in {1, 2, 4}, "Invalid byte size"
    if per_line is None:
        per_line = 16 // size
    end = addr + length
    inc = per_line * size
    for i in range(addr, end, inc):
        j = min(i + inc, end)
        if size == 1:
            print(" ".join(f"{b:02X}" for b in rom.data[i:j]))
        elif size == 2:
            print(" ".join(f"{rom.read_16(a):04X}" for a in range(i, j, 2)))
        elif size == 4:
            print(" ".join(f"{rom.read_32(a):08X}" for a in range(i, j, 4)))


def all_funcs(rom: Rom) -> list[tuple[int, int]]:
    """
    Returns (addr, size) pairs for every function in the ROM.
    """
    funcs = all_functions(rom)
    sizes = [(f.start_addr, f.end_addr - f.start_addr) for f in funcs]
    sizes += [(k, v - k) for k, v in rom.arm_functions().items()]
    sizes.sort()
    return sizes


def coverage(rom: Rom):
    info = GameInfo(rom.game, rom.region)
    # Get total size of code entries
    code_cov = 0
    for entry in info.code:
        code_cov += entry.size
    # Get total size of data entries
    data_cov = 0
    for entry in info.data:
        data_cov += entry.get_size(info.structs)
    # Compute percent of rom covered
    code_size = rom.code_end() - 0xC0
    data_size = rom.data_end() - rom.data_start()
    rom_size = code_size + data_size
    print(f"Code:\t{code_cov / code_size:.2%}")
    print(f"Data:\t{data_cov / data_size:.2%}")
    print(f"Total:\t{(code_cov + data_cov) / rom_size:.2%}")


class FindPtrData(object):

    def __init__(self, rom: Rom):
        self.rom = rom
        self.data_start = rom.data_start()
        self.data_end = rom.data_end()
        self.info = GameInfo(rom.game, rom.region, InfoSource.YAML_UNK)
        self.data_set = {d.addr for d in self.info.data}
        self.results = defaultdict(list)

    def find(self):
        for entry in self.info.data:
            self.check_entry(entry)
        for addr in sorted(self.results):
            names = ", ".join(self.results[addr])
            print(f"{addr:X}: {names}")

    def check_entry(self,
        entry: VarEntry,
        base_addr: int = None,
        base_name: str = None
    ):
        if base_addr is None:
            base_addr = entry.addr
            base_name = entry.name
        else:
            base_addr = base_addr + entry.offset
            base_name = base_name + "_" + entry.name
        count = entry.get_count()
        if entry.is_ptr():
            base_name = re.sub("Ptrs?$", "", base_name)
            for i in range(count):
                addr = rom.read_32(base_addr + i * 4)
                if addr < ROM_OFFSET:
                    continue
                addr -= ROM_OFFSET
                if (addr >= self.data_start and
                    addr < self.data_end and
                    addr not in self.data_set):
                    name = base_name
                    if count > 1:
                        name += f"_{i:02X}"
                    self.results[addr].append(name)
        elif entry.struct_name() is not None:
            struct = self.info.get_struct(entry.struct_name())
            for i in range(count):
                addr = base_addr + i * struct.size
                name = base_name
                if count > 1:
                    name += f"_{i:02X}"
                for var in struct.vars:
                    self.check_entry(var, addr, name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    subparsers = parser.add_subparsers(dest="command")
    # bytes command
    subparser = subparsers.add_parser("bytes",
        help="Dumps raw bytes from the ROM")
    apu.add_arg(subparser, apu.ArgType.ADDR)
    subparser.add_argument("length", type=str)
    subparser.add_argument("-s", "--size", type=int,
        choices=[1, 2, 4], default=1)
    subparser.add_argument("-l", "--per_line", type=str)
    # all_funcs command
    subparser = subparsers.add_parser("all_funcs",
        help="Prints all function addresses and their sizes")
    # coverage command
    subparser = subparsers.add_parser("coverage",
        help="Computes the percent of ROM code and data with labeled entries")
    # ptr_data command
    subparser = subparsers.add_parser("ptr_data",
        help="Follows pointers to find unlabeled data")

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    if args.command == "bytes":
        addr = apu.get_hex(args.addr)
        length = int(args.length, 16)
        per_line = int(args.per_line, 16) if args.per_line else None
        dump_bytes(rom, addr, length, args.size, per_line)
    elif args.command == "all_funcs":
        funcs = all_funcs(rom)
        for addr, size in funcs:
            print(f"{addr:X}\t{size:X}")
    elif args.command == "coverage":
        coverage(rom)
    elif args.command == "ptr_data":
        fpd = FindPtrData(rom)
        fpd.find()
    else:
        parser.print_help()
