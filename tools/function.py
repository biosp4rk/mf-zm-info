from typing import Dict, List, Set, Tuple
from rom import Rom, ROM_OFFSET
from thumb import *


class Function(object):
    INDENT = " " * 4
    DOT_POOL = ".pool"

    # TODO: fix symbols
    def __init__(self, rom: Rom, addr: int):
        self.rom = rom
        self.addr = addr
        self.symbols = {}
        self.start_addr = addr
        self.end_addr = -1
        self.instructs: Dict[int, ThumbInstruct] = {}
        self.jump_tables: Set[int] = set()
        self.branches: Set[int] = set()
        self.data_pool: Set[int] = set()
        self.at_end = False
        self.at_jump = False
        self.step_through()

    def get_instructions(self) -> List[ThumbInstruct]:
        return list(self.instructs.values())

    def step_through(self) -> None:
        # step through each instruction
        while not self.at_end:
            # skip if in data pool
            if self.addr in self.data_pool:
                self.addr += 4
                continue

            # get current instruction
            inst = ThumbInstruct(self.rom, self.addr)

            # check for branches, data pools, jump tables, and end of function
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

            # add current instruction to dictionary
            self.instructs[self.addr] = inst
            
            # increment address
            if inst.format == ThumbForm.Link:
                self.addr += 4
            else:
               self.addr += 2

            # check if at jump
            if self.at_jump:
                self.handle_jump()

        # find end of last data pool (if present)
        self.align(4)
        while (self.addr in self.data_pool):
            self.addr += 4
        self.end_addr = self.addr

        # find any BLs that are local branches
        for inst in self.instructs.values():
            if inst.format == ThumbForm.Link:
                pa = inst.branch_addr()
                if pa > self.start_addr and pa < self.end_addr:
                    self.branches.add(pa)

    def align(self, num: int) -> None:
        r = self.addr % num
        if r != 0:
            self.addr += num - r

    def handle_jump(self) -> None:
        # find start of table (should start after data pool)
        self.align(4)
        while self.addr in self.data_pool:
            self.addr += 4
        # add offset to jump tables and symbols
        self.jump_tables.add(self.addr)
        self.symbols[self.addr + ROM_OFFSET] = f"@@_{self.addr:X}"
        # find all branches in table
        while True:
            if self.addr in self.branches:
                break
            jump = self.rom.read_ptr(self.addr)
            self.branches.add(jump)
            self.addr += 4
        self.at_jump = False

    def get_jump_tables(self) -> Set[int]:
        jumps = set()
        for start in self.jump_tables:
            offset = start
            while offset not in self.branches:
                jumps.add(offset)
                offset += 4
        return jumps

    def get_data_pools(self) -> List[Tuple[int, int]]:
        # returns (address, size) pairs of each data pool
        pools: List[Tuple[int, int]] = []
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
