import argparse

import argparse_utils as apu
from function import all_functions
from info.game_info import GameInfo
from rom import Rom


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
    else:
        parser.print_help()
