import argparse
from typing import List, Tuple

import argparse_utils as apu
from function import Function
from game_info import GameInfo
from rom import Rom


def dump_bytes(rom: Rom, addr: int, length: int, size: int = 1):
    assert size in {1, 2, 4}, "Invalid byte size"
    end = addr + length
    for i in range(addr, end, 16):
        j = min(i + 16, end)
        if size == 1:
            print(" ".join(f"{b:02X}" for b in rom.data[i:j]))
        elif size == 2:
            print(" ".join(f"{rom.read16(a):04X}" for a in range(i, j, 2)))
        elif size == 4:
            print(" ".join(f"{rom.read32(a):08X}" for a in range(i, j, 4)))


def all_funcs(rom: Rom) -> List[Tuple[int, int]]:
    addr = rom.code_start()
    code_end = rom.code_end()
    arm_funcs = rom.arm_functions()
    all_funcs: List[Tuple[int, int]] = []
    while addr < code_end:
        end = None
        size = None
        if addr in arm_funcs:
            end = arm_funcs[addr]
        else:
            func = Function(rom, addr)
            end = func.end_addr
        size = end - addr
        all_funcs.append((addr, size))
        addr = end
    return all_funcs


def coverage(rom: Rom):
    info = GameInfo(rom.game, rom.region)
    # get total size of code entries
    code_cov = 0
    for entry in info.code:
        code_cov += entry.size
    # get total size of data entries
    data_cov = 0
    for entry in info.data:
        data_cov += entry.get_size(info.structs)
    # compute percent of rom covered
    code_size = rom.code_end() - 0xC0
    data_size = rom.data_end() - rom.data_start()
    rom_size = code_size + data_size
    print(f"Code:\t{code_cov / code_size:.2%}")
    print(f"Data:\t{data_cov / data_size:.2%}")
    print(f"Total:\t{(code_cov + data_cov) / rom_size:.2%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    # bytes command
    subparser = subparsers.add_parser("bytes")
    apu.add_arg(subparser, apu.ArgType.ROM_PATH)
    apu.add_arg(subparser, apu.ArgType.ADDR)
    subparser.add_argument("count", type=str)
    subparser.add_argument("-s", "--size", type=int,
        choices=[1, 2, 4], default=1)
    # all_funcs command
    subparser = subparsers.add_parser("all_funcs")
    apu.add_arg(subparser, apu.ArgType.ROM_PATH)
    # coverage command
    subparser = subparsers.add_parser("coverage")
    apu.add_arg(subparser, apu.ArgType.ROM_PATH)

    args = parser.parse_args()
    if args.command == "bytes":
        rom = apu.get_rom(args.rom_path)
        addr = apu.get_hex(args.addr)
        count = int(args.count, 16)
        dump_bytes(rom, addr, count, args.size)
    elif args.command == "all_funcs":
        rom = apu.get_rom(args.rom_path)
        funcs = all_funcs(rom)
        for addr, size in funcs:
            print(f"{addr:X}\t{size:X}")
    elif args.command == "coverage":
        rom = apu.get_rom(args.rom_path)
        coverage(rom)
    else:
        parser.print_help()
