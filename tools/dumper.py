import argparse
from typing import List, Tuple

from function import Function
from rom import Rom


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    parser1 = subparsers.add_parser("all_funcs")
    parser1.add_argument("rom_path", type=str)
    args = parser.parse_args()

    if args.command == "all_funcs":
        rom = Rom(args.rom_path)
        funcs = all_funcs(rom)
        for addr, size in funcs:
            print(f"{addr:X}\t{size:X}")
