import argparse
from typing import Dict, List, Set

from constants import *
from function import Function
from game_info import GameInfo
from rom import Rom
from symbols import Symbols
from thumb import ThumbForm


class CallStack(object):
    def __init__(self, rom: Rom, addr: int, symbols: Symbols = Symbols()):
        self.rom = rom
        self.info = GameInfo(rom.game, rom.region)
        self.symbols = symbols
        self.stack = self.recurse(addr, 0, set())

    def recurse(self, addr: int, depth: int, seen: Set[int]) -> Dict[str, Dict]:
        func = Function(self.rom, addr, self.symbols)
        stack: Dict[str, Dict] = {}
        for inst in func.instructs.values():
            if inst.format != ThumbForm.Link:
                continue
            offset = inst.branch_addr()
            # skip if we've already seen this function
            if offset in seen:
                continue
            # skip if bl used as branch within function
            if offset >= func.start_addr and offset < func.end_addr:
                continue
            seen.add(offset)
            stack[offset] = self.recurse(offset, depth + 1, seen)
        return stack

    def get_lines(self, indent: int = 2) -> List[str]:
        lines = []
        self.add_lines(self.stack, 0, indent, lines)
        return lines
    
    def add_lines(self, 
        subs: Dict[int, Dict],
        depth: int,
        indent: int,
        lines: List[str]
    ):
        tab = depth * indent * " "
        for addr, calls in subs.items():
            line = f"{tab}{addr:05X}"
            entry = self.info.get_entry_by_addr(addr)
            if entry:
                line += f" {entry.label}"
            lines.append(line)
            self.add_lines(calls, depth + 1, indent, lines)


if __name__ == "__main__":
    import argparse_utils as apu
    parser = argparse.ArgumentParser()
    apu.add_rom_path_arg(parser)
    apu.add_addr_arg(parser)

    args = parser.parse_args()
    rom = apu.get_rom(args)
    addr = apu.get_addr(args)

    call_stack = CallStack(rom, addr)
    for line in call_stack.get_lines(2):
        print(line)
