import argparse
from typing import List, Tuple

from function import Function
from rom import Rom


def dump_bytes(rom: Rom, start: int, length: int):
    end = start + length
    for i in range(start, end, 16):
        j = min(i + 16, end)
        print(" ".join(f"{b:02X}" for b in rom.data[i:j]))


def all_funcs(rom: Rom) -> List[Tuple[int, int]]:
    addr = rom.code_start()
    code_end = rom.code_end()
    print(f"{code_end:X}")
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
    from game_info import GameInfo
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
    rom_size = rom.data_end() - 0xC0
    print(f"Code:\t{code_cov / code_size:.2%}")
    print(f"Data:\t{data_cov / data_size:.2%}")
    print(f"Total:\t{(code_cov + data_cov) / rom_size:.2%}")


if __name__ == "__main__":
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    # bytes command
    subparser = subparsers.add_parser("bytes")
    apu.add_rom_path_arg(subparser)
    apu.add_addr_arg(subparser)
    subparser.add_argument("count", type=str)
    # all_funcs command
    subparser = subparsers.add_parser("all_funcs")
    apu.add_rom_path_arg(subparser)
    # coverage command
    subparser = subparsers.add_parser("coverage")
    apu.add_rom_path_arg(subparser)

    args = parser.parse_args()
    if args.command == "bytes":
        rom = apu.get_rom(args)
        addr = apu.get_addr(args)
        count = int(args.count, 16)
        dump_bytes(rom, addr, count)
    elif args.command == "all_funcs":
        rom = apu.get_rom(args)
        funcs = all_funcs(rom)
        for addr, size in funcs:
            print(f"{addr:X}\t{size:X}")
    elif args.command == "coverage":
        rom = apu.get_rom(args)
        coverage(rom)
    else:
        parser.print_help()
