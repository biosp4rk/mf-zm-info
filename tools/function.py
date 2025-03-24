import argparse
from collections.abc import Iterator
from enum import Enum, auto

import argparse_utils as apu
from constants import *
from game_info import GameInfo
from info_entry import CodeMode
from rom import Rom, ROM_OFFSET
from symbols import LabelType, Symbols
from thumb import *


class Function(object):

    INDENT = " " * 4
    DOT_POOL = ".pool"

    def __init__(self, rom: Rom, addr: int, symbols: Symbols = Symbols()):
        self.rom = rom
        self.symbols = symbols
        self.start_addr = addr
        self.end_addr = -1
        self.instructs: dict[int, ThumbInstruct] = {}
        self.jump_tables: set[int] = set()
        self.branches: set[int] = set()
        self.data_pool: set[int] = set()
        self.at_end = False
        self.at_jump = False
        self.locals: set[int] = None
        self.local_indexes: dict[int, int] = None
        self.step_through()

    def get_instructions(self) -> list[ThumbInstruct]:
        keys = sorted(self.instructs.keys())
        return [self.instructs[a] for a in keys]

    def step_through(self) -> None:
        self.addr = self.start_addr
        # Step through each instruction
        while not self.at_end:
            # Skip if in data pool
            if self.in_data_pool():
                self.align(4)
                self.addr += 4
                continue

            # Get current instruction
            inst = ThumbInstruct(self.rom, self.addr)

            # Check for branches, data pools, jump tables, and end of function
            if inst.format == ThumbForm.HiReg:
                if inst.opname == ThumbOp.MOV:
                    if inst.rd == 15:
                        if inst.rs == 14:
                            # mov r15,r14
                            self.at_end = True
                        else:
                            # mov r15,Rs
                            self.at_jump = True
                elif inst.opname == ThumbOp.BX:
                    # bx Rs
                    self.at_end = True
            elif inst.format == ThumbForm.LdPC:
                # ldr Rd,=Word
                self.data_pool.add(inst.pc_rel_addr())
            elif inst.format == ThumbForm.PushPop:
                if inst.opname == ThumbOp.POP and 15 in inst.rlist:
                    # pop r15
                    self.at_end = True
            elif (inst.format == ThumbForm.CondB or
                inst.format == ThumbForm.UncondB):
                self.branches.add(inst.branch_addr())

            # Add current instruction to dictionary
            self.instructs[self.addr] = inst
            
            # Increment address
            if inst.format == ThumbForm.Link:
                self.addr += 4
            else:
                self.addr += 2

            # Check if at jump
            if self.at_jump:
                self.handle_jump()

        # Find end of last data pool (if present)
        self.align(4)
        while (self.addr in self.data_pool):
            self.addr += 4
        self.end_addr = self.addr

        # Find any BLs that are local branches
        for inst in self.instructs.values():
            if inst.format == ThumbForm.Link:
                pa = inst.branch_addr()
                if pa > self.start_addr and pa < self.end_addr:
                    self.branches.add(pa)

        # Add local labels for branches
        for branch in self.branches:
            self.symbols.add_local(branch)
        self.symbols.finalize_locals()
        self.locals = self.symbols.locals
        self.local_indexes = self.symbols.local_indexes
        self.symbols.reset_locals()
        delattr(self, "addr")

    def align(self, num: int) -> None:
        r = self.addr % num
        if r != 0:
            self.addr += num - r

    def handle_jump(self) -> None:
        # Find start of table (should start after data pool)
        self.align(4)
        while self.addr in self.data_pool:
            self.addr += 4
        # Add offset to jump tables and symbols
        self.jump_tables.add(self.addr)
        self.symbols.add_local(self.addr)
        # Find all branches in table
        while True:
            if self.addr in self.branches:
                break
            jump = self.rom.read_ptr(self.addr)
            self.branches.add(jump)
            self.addr += 4
        self.at_jump = False

    def get_jump_tables(self) -> set[int]:
        jumps = set()
        for start in self.jump_tables:
            offset = start
            while offset not in self.branches:
                jumps.add(offset)
                offset += 4
        return jumps

    def in_data_pool(self) -> bool:
        return self.addr in self.data_pool or (
            self.addr % 4 == 2 and
            self.rom.read_16(self.addr) == 0 and
            self.addr + 2 in self.data_pool
        )

    def get_data_pools(self) -> list[tuple[int, int]]:
        # Returns (address, size) pairs of each data pool
        pools: list[tuple[int, int]] = []
        all_words = self.data_pool | self.get_jump_tables()
        if len(all_words) == 0:
            return pools
        addrs = sorted(all_words)

        prev_addr = addrs[0]
        pools.append((prev_addr, 4))
        for addr in addrs[1:]:
            if addr == prev_addr + 4:
                start, size = pools[-1]
                pools[-1] = (start, size + 4)
            else:
                pools.append((addr, 4))
            prev_addr = addr
        return pools

    def get_symbols(self) -> dict[int, str]:
        syms = {}
        # Find all bls
        for inst in self.instructs.values():
            if inst.format == ThumbForm.Link:
                addr = inst.branch_addr()
                # Skip if within this function
                if addr >= self.start_addr and addr < self.end_addr:
                    continue
                addr += ROM_OFFSET
                label = self.symbols.get_label(addr, LabelType.Code)
                syms[addr] = label
        # Check all data pools
        pools = self.get_data_pools()
        rom_start = self.rom.code_start(True)
        rom_end = self.rom.data_end(True)
        code_end = self.rom.code_end()
        for addr, size in pools:
            end = addr + size
            for i in range(addr, end, 4):
                val = self.rom.read_32(i)
                # Check if in ram
                if (
                    (val >= 0x2000000 and val < 0x2040000) or
                    (val >= 0x3000000 and val < 0x3008000)
                ):
                    label = self.symbols.get_label(val, LabelType.Data)
                    syms[val] = label
                # Check if in rom
                elif val >= rom_start and val < rom_end:
                    pa = val - ROM_OFFSET
                    label_type: LabelType = None
                    if pa < code_end:
                        # Skip if within this function
                        if pa >= self.start_addr and pa < self.end_addr:
                            continue
                        label_type = LabelType.Code
                        val -= 1
                    else:
                        label_type = LabelType.Data
                    label = self.symbols.get_label(val, label_type)
                    syms[val] = label
        return syms

    def get_lines(self, include_syms: bool, include_addrs: bool = False) -> list[str]:
        self.symbols.locals = self.locals
        self.symbols.local_indexes = self.local_indexes

        lines = []
        if include_syms:
            syms = self.get_symbols()
            syms = sorted(syms.items())
            for addr, label in syms:
                lines.append(f".definelabel {label},0x{addr:X}")
            lines.append("")

        # Add address
        lines.append(f"; {self.start_addr:X}")

        # Get label for function name
        func_addr = self.start_addr + ROM_OFFSET
        label = self.symbols.get_label(func_addr, LabelType.Code)
        lines.append(label + ":")

        # Add size
        size = self.end_addr - self.start_addr
        lines.append(f"; Size: {size:X}")

        # Go until end of function
        self.addr = self.start_addr
        in_pool = False
        while self.addr < self.end_addr:
            # Check if anything branches to current offset
            if self.addr in self.branches:
                lines.append(self.symbols.get_local(self.addr) + ":")
            if self.in_data_pool():
                # If already in a data pool, do nothing
                # If just entered a data pool, write .pool
                if not in_pool:
                    lines.append(self.INDENT + self.DOT_POOL)
                    in_pool = True
                    self.align(4)
                self.addr += 4
            elif self.addr in self.jump_tables:
                lines.append(self.symbols.get_local(self.addr) + ":")
                jumps = []
                while True:
                    if self.addr in self.branches:
                        break
                    jump = self.rom.read_ptr(self.addr)
                    jumps.append(self.symbols.get_local(jump))
                    self.addr += 4
                num_jumps = len(jumps)
                for j in range(0, num_jumps, 4):
                    end = j + min(4, num_jumps - j)
                    jump_labels = ",".join(jumps[j:end])
                    lines.append(f"{self.INDENT}.dw {jump_labels}")
                in_pool = False
            elif self.addr in self.instructs:
                inst = self.instructs[self.addr]
                asm_str = inst.asm_str(self.rom, self.symbols, self.branches)
                if include_addrs:
                    asm_str = f"{asm_str:35} ; {self.addr:X}"
                lines.append("    " + asm_str)
                if inst.format == ThumbForm.Link:
                    self.addr += 4
                else:
                    self.addr += 2
                in_pool = False
            elif self.addr + 2 == self.end_addr:
                break
            else:
                err = f"Unsure what to output at {self.addr:X}"
                raise ValueError(err)
        self.symbols.reset_locals()
        delattr(self, "addr")
        return lines


class FuncDiff(Enum):

    DIFF_SIZE = auto()
    """Functions are different sizes."""
    DIFF_INST = auto()
    """Functions have at least one instruction that is different."""
    SAME_WITH_BL = auto()
    """Functions are the same, but have a bl instruction."""
    IDENTICAL = auto()
    """Functions are identical."""

    def is_same(self) -> bool:
        return self == FuncDiff.SAME_WITH_BL or self == FuncDiff.IDENTICAL


def compare(func_a: Function, func_b: Function) -> FuncDiff:
    # Get instructions of both functions
    instructs_a = func_a.get_instructions()
    instructs_b = func_b.get_instructions()
    num_instructs = len(instructs_a)
    if num_instructs != len(instructs_b):
        return FuncDiff.DIFF_SIZE
    # Compare each instruction in order
    has_bl = False
    for i in range(num_instructs):
        self_inst = instructs_a[i]
        other_inst = instructs_b[i]
        if self_inst.format != other_inst.format:
            return FuncDiff.DIFF_INST
        if self_inst.format == ThumbForm.Link:
            has_bl = True
        elif str(self_inst) != str(other_inst):
            return FuncDiff.DIFF_INST
    return FuncDiff.SAME_WITH_BL if has_bl else FuncDiff.IDENTICAL


def compare_all(rom_a: Rom, rom_b: Rom) -> None:
    region_a = rom_a.region
    region_b = rom_b.region
    assert rom_a.game == rom_b.game and region_a != region_b
    info = GameInfo(rom_a.game)
    for entry in info.code:
        if entry.mode == CodeMode.Arm:
            continue
        addr_a = entry.addr.get(region_a)
        addr_b = entry.addr.get(region_b)
        msg = None
        if addr_a is not None and addr_b is not None:
            func_a = Function(rom_a, addr_a)
            func_b = Function(rom_b, addr_b)
            diff = compare(func_a, func_b)
            if not diff.is_same():
                msg = diff.name
        elif addr_a is not None:
            msg = f"{region_a} only"
        elif addr_b is not None:
            msg = f"{region_b} only"
        if msg is not None:
            addr_str_a = "" if addr_a is None else f"{addr_a:X}"
            addr_str_b = "" if addr_b is None else f"{addr_b:X}"
            print("\t".join([entry.name, msg, addr_str_a, addr_str_b]))



def all_functions(rom: Rom) -> Iterator[Function]:
    """
    Returns every THUMB function in the ROM.
    """
    addr = rom.code_start()
    code_end = rom.code_end()
    arm_funcs = rom.arm_functions()
    while addr < code_end:
        if addr in arm_funcs:
            addr = arm_funcs[addr]
        else:
            func = Function(rom, addr)
            yield func
            addr = func.end_addr


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--addr", type=str)
    group.add_argument("-n", "--name", type=str)
    parser.add_argument("-s", "--symbols", action="store_true")
    parser.add_argument("-c", "--addr_comments", action="store_true")

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    
    # Load symbols
    info = GameInfo(rom.game, rom.region)
    syms = Symbols(info)

    # Get address
    addr = None
    if args.addr:
        try:
            addr = int(args.addr, 16)
        except:
            print(f"Invalid hex address {args.addr}")
            quit()
    elif args.name:
        entry = info.get_code(args.name)
        if entry is None:
            print("Name not found")
            quit()
        addr = entry.addr

    # Print function
    func = Function(rom, addr, syms)
    lines = func.get_lines(args.symbols, args.addr_comments)
    print("\n".join(lines))
