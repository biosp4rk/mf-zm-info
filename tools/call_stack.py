import argparse

import argparse_utils as apu
from constants import *
from function import Function
from info.game_info import GameInfo
from rom import Rom
from symbols import Symbols
from thumb import ThumbForm


class CallStack(object):

    def __init__(self, rom: Rom, addr: int, symbols: Symbols = Symbols()):
        self.rom = rom
        self.info = GameInfo(rom.game, rom.region)
        self.symbols = symbols
        self.stack = self.recurse(addr, 0, set())

    def recurse(self, addr: int, depth: int, seen: set[int]) -> dict[str, dict]:
        func = Function(self.rom, addr, self.symbols)
        stack: dict[str, dict] = {}
        for inst in func.instructs.values():
            if inst.format != ThumbForm.Link:
                continue
            offset = inst.branch_addr()
            # Skip if we've already seen this function
            if offset in seen:
                continue
            # Skip if bl used as branch within function
            if offset >= func.start_addr and offset < func.end_addr:
                continue
            seen.add(offset)
            stack[offset] = self.recurse(offset, depth + 1, seen)
        return stack

    def get_lines(self, indent: int = 2) -> list[str]:
        lines = []
        self.add_lines(self.stack, 0, indent, lines)
        return lines
    
    def add_lines(self, 
        subs: dict[int, dict],
        depth: int,
        indent: int,
        lines: list[str]
    ):
        tab = depth * indent * " "
        for addr, calls in subs.items():
            line = f"{tab}{addr:05X}"
            entry = self.info.get_entry_by_addr(addr)
            if entry:
                line += f" {entry.name}"
            lines.append(line)
            self.add_lines(calls, depth + 1, indent, lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    apu.add_arg(parser, apu.ArgType.ADDR)

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    addr = apu.get_hex(args.addr)

    call_stack = CallStack(rom, addr)
    for line in call_stack.get_lines(2):
        print(line)
