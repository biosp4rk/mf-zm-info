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
    parser1 = subparsers.add_parser("bytes")
    parser1.add_argument("rom_path", type=str)
    parser1.add_argument("addr", type=str)
    parser1.add_argument("count", type=str)
    parser1 = subparsers.add_parser("all_funcs")
    parser1.add_argument("rom_path", type=str)
    args = parser.parse_args()

    if args.command == "bytes":
        rom = Rom(args.rom_path)
        addr = int(args.addr, 16)
        count = int(args.count, 16)
        dump_bytes(rom, addr, count)
    if args.command == "all_funcs":
        rom = Rom(args.rom_path)
        funcs = all_funcs(rom)
        for addr, size in funcs:
            print(f"{addr:X}\t{size:X}")
