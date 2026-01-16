from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto

from function import Function
from rom import Rom, ROM_OFFSET
from symbols import Symbols, LabelType
from thumb import ThumbInstruct, ThumbOp, ThumbForm, Reg


INDENT = " " * 4
DOT_POOL = ".pool"


class BranchFormat(Enum):
    ORDERED = auto()
    ADDRESS = auto()


class CommentChar(Enum):
    SEMICOLON = auto()
    AT = auto()


class AsmFormat(Enum):
    ARMIPS = auto()
    DECOMP_ME = auto()
    DECOMP_REPO = auto()


@dataclass(frozen=True)
class FormatOptions:
    unified: bool
    comma_space: bool
    branch_format: BranchFormat
    prefixed_local: bool
    prefixed_immed: bool
    braced_reg_list: bool
    reg_list_range: bool
    data_directive: str
    dot_pool: bool
    comment_char: CommentChar
    # TODO: Add hex format, lr/pc vs r14/15, pool format


FORMAT_OPTIONS = {
    AsmFormat.ARMIPS: FormatOptions(
        unified=False,
        comma_space=False,
        branch_format=BranchFormat.ORDERED,
        prefixed_local=True,
        prefixed_immed=False,
        braced_reg_list=False,
        reg_list_range=True,
        data_directive=".dw",
        dot_pool=True,
        comment_char=CommentChar.SEMICOLON,
    ),
    AsmFormat.DECOMP_ME: FormatOptions(
        unified=False,
        comma_space=True,
        branch_format=BranchFormat.ADDRESS,
        prefixed_local=False,
        prefixed_immed=True,
        braced_reg_list=True,
        reg_list_range=False,
        data_directive=".word",
        dot_pool=True,
        comment_char=CommentChar.AT,
    ),
    AsmFormat.DECOMP_REPO: FormatOptions(
        unified=True,
        comma_space=True,
        branch_format=BranchFormat.ADDRESS,
        prefixed_local=False,
        prefixed_immed=True,
        braced_reg_list=True,
        reg_list_range=False,
        data_directive=".4byte",
        dot_pool=False,
        comment_char=CommentChar.AT,
    ),
}


class AsmWriter:

    def __init__(self,
        rom: Rom,
        symbols: Symbols,
        branches: set[int],
        format_opts: FormatOptions
    ):
        self.rom = rom
        self.symbols = symbols
        self.branches = branches
        self.format_opts = format_opts
        match format_opts.comment_char:
            case CommentChar.SEMICOLON:
                self.comment_char = ";"
            case CommentChar.AT:
                self.comment_char = "@"
    
    @classmethod
    def create(cls,
        rom: Rom,
        symbols: Symbols,
        branches: set[int],
        asm_format: AsmFormat
    ) -> "AsmWriter":
        format_opts = FORMAT_OPTIONS[asm_format]
        return cls(rom, symbols, branches, format_opts)

    def function_str(self,
        func: Function,
        include_syms: bool,
        include_addrs: bool = False
    ) -> str:
        self.symbols.locals = func.locals
        self.symbols.local_indexes = func.local_indexes

        lines = []
        if include_syms:
            # TODO: Handle non-armips syntax
            syms = self._get_func_symbols(func)
            syms = sorted(syms.items())
            for addr, label in syms:
                lines.append(f".definelabel {label},0x{addr:X}")
            lines.append("")

        if self.format_opts.unified:
            lines.append(".syntax unified")
            lines.append("")

        # Add address
        lines.append(f"{self.comment_char} {func.start_addr:X}")

        # Get label for function name
        func_addr = func.start_addr + ROM_OFFSET
        label = self._get_label(func_addr, LabelType.Code)
        if self.format_opts.unified:
            lines.append(f"thumb_func_start {label}")
        lines.append(label + ":")

        # Add size
        size = func.end_addr - func.start_addr
        lines.append(f"{self.comment_char} Size: {size:X}")

        # Go until end of function
        func.addr = func.start_addr
        dd = self.format_opts.data_directive
        in_pool = False
        cases: defaultdict[int, list[int]] = defaultdict(list)
        while func.addr < func.end_addr:
            # Check if anything branches to current offset
            if func.addr in self.branches:
                line = self._get_local(func.addr) + ":"
                if func.addr in cases:
                    case_nums = ", ".join(str(c) for c in cases[func.addr])
                    line += f" {self.comment_char} case {case_nums}"
                lines.append(line)
            if func.in_data_pool():
                if self.format_opts.dot_pool:
                    # If already in a data pool, do nothing
                    # If just entered a data pool, write .pool
                    if not in_pool:
                        lines.append(INDENT + DOT_POOL)
                        in_pool = True
                        func.align(4)
                else:
                    if not in_pool:
                        lines.append(f"{INDENT}.align 2, 0")
                        in_pool = True
                        func.align(4)
                    addr_str = self._get_local(func.addr)
                    word = self.rom.read_32(func.addr)
                    label = self._get_label(word, LabelType.Imm)
                    lines.append(f"{addr_str}: {dd} {label}")
                func.addr += 4
            elif func.addr in func.jump_tables:
                addr_str = self._get_local(func.addr)
                lines.append(f"{addr_str}: {self.comment_char} jump table")
                jumps = []
                c = 0
                while True:
                    if func.addr in self.branches:
                        break
                    jump = self.rom.read_ptr(func.addr)
                    jumps.append(self._get_local(jump))
                    cases[jump].append(c)
                    func.addr += 4
                    c += 1
                if self.format_opts.unified:
                    for i, jump in enumerate(jumps):
                        lines.append(f"{INDENT}.4byte {jump} {self.comment_char} case {i}")
                else:
                    num_jumps = len(jumps)
                    for j in range(0, num_jumps, 4):
                        end = j + min(4, num_jumps - j)
                        jump_labels = self._comma_join(jumps[j:end])
                        lines.append(f"{INDENT}{dd} {jump_labels}")
                in_pool = False
            elif func.addr in func.instructs:
                instruct = func.instructs[func.addr]
                asm_str = self.instruct_str(instruct)
                if include_addrs:
                    asm_str = f"{asm_str:35} {self.comment_char} {func.addr:X}"
                lines.append("    " + asm_str)
                if instruct.format == ThumbForm.Link:
                    func.addr += 4
                else:
                    func.addr += 2
                in_pool = False
            elif func.addr + 2 == func.end_addr:
                break
            else:
                err = f"Unsure what to output at {func.addr:X}"
                raise ValueError(err)
        self.symbols.reset_locals()
        delattr(func, "addr")
        return "\n".join(lines)

    def instruct_str(self, instruct: ThumbInstruct) -> str:
        args = []
        if instruct.format == ThumbForm.Shift:
            args.append(f"r{instruct.rd}")
            args.append(f"r{instruct.rs}")
            args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.AddSub:
            args.append(f"r{instruct.rd}")
            args.append(f"r{instruct.rs}")
            if instruct.opname != ThumbOp.MOV:
                if instruct.rn is not None:
                    args.append(f"r{instruct.rn}")
                else:
                    args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.Immed:
            args.append(f"r{instruct.rd}")
            args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.AluOp:
            args.append(f"r{instruct.rd}")
            args.append(f"r{instruct.rs}")
        elif instruct.format == ThumbForm.HiReg:
            if instruct.opname != ThumbOp.NOP:
                if (instruct.opname == ThumbOp.ADD or
                    instruct.opname == ThumbOp.CMP or
                    instruct.opname == ThumbOp.MOV):
                    args.append(f"r{instruct.rd}")
                args.append(f"r{instruct.rs}")
        elif instruct.format == ThumbForm.LdPC:
            args.append(f"r{instruct.rd}")
            addr = instruct.pc_rel_addr()
            word = self.rom.read_32(addr)
            label = self._get_label(word, LabelType.Imm)
            if self.format_opts.unified:
                addr_str = self._get_local(addr)
                args.append(f"{addr_str} {self.comment_char} ={label}")
            else:
                args.append("=" + label)
        elif (instruct.format == ThumbForm.LdStR or
            instruct.format == ThumbForm.LdStRS):
            args.append(f"r{instruct.rd}")
            args.append(f"[r{instruct.rs}")
            args.append(f"r{instruct.ro}]")
        elif (instruct.format == ThumbForm.LdStI or
            instruct.format == ThumbForm.LdStIH):
            args.append(f"r{instruct.rd}")
            if instruct.imm == 0:
                args.append(f"[r{instruct.rs}]")
            else:
                args.append(f"[r{instruct.rs}")
                args.append(f"{self._imm_str(instruct)}]")
        elif instruct.format == ThumbForm.LdStSP:
            args.append(f"r{instruct.rd}")
            if instruct.imm == 0:
                args.append("[sp]")
            else:
                args.append("[sp")
                args.append(f"{self._imm_str(instruct)}]")
        elif instruct.format == ThumbForm.RelAddr:
            args.append(f"r{instruct.rd}")
            if instruct.rs == Reg.PC:
                pa = instruct.pc_rel_addr()
                if pa in self.branches:
                    args.append(self._get_local(pa))
                else:
                    va = pa + ROM_OFFSET
                    args.append("=" + self._get_label(va, LabelType.Imm))
            else:
                args.append("sp")
                args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.AddSP:
            args.append("sp")
            args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.PushPop:
            args.append(self._rlist_str(instruct))
        elif instruct.format == ThumbForm.LdStM:
            args.append(f"r{instruct.rd}!")
            args.append(self._rlist_str(instruct))
        elif (instruct.format == ThumbForm.CondB or
            instruct.format == ThumbForm.UncondB):
            pa = instruct.branch_addr()
            if pa in self.branches:
                args.append(self._get_local(pa))
            else:
                va = pa + ROM_OFFSET
                args.append(self._get_label(va, LabelType.Imm))
        elif instruct.format == ThumbForm.Swi:
            args.append(self._imm_str(instruct))
        elif instruct.format == ThumbForm.Link:
            pa = instruct.branch_addr()
            if pa in self.branches:
                args.append(self._get_local(pa))
            else:
                va = pa + ROM_OFFSET
                args.append(self._get_label(va, LabelType.Code))
        else:
            raise ValueError()
        
        lhs = instruct.opname.name.lower()
        rhs = self._comma_join(args)
        if rhs == "":
            return f"{lhs}"
        return f"{lhs:8}{rhs}"

    def _get_func_symbols(self, func: Function) -> dict[int, str]:
        syms = {}
        # Find all bls
        for inst in func.instructs.values():
            if inst.format == ThumbForm.Link:
                addr = inst.branch_addr()
                # Skip if within this function
                if addr >= func.start_addr and addr < func.end_addr:
                    continue
                addr += ROM_OFFSET
                label = self._get_label(addr, LabelType.Code)
                syms[addr] = label
        # Check all data pools
        pools = func.get_data_pools()
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
                    label = self._get_label(val, LabelType.Data)
                    syms[val] = label
                # Check if in rom
                elif val >= rom_start and val < rom_end:
                    pa = val - ROM_OFFSET
                    label_type: LabelType = None
                    if pa < code_end:
                        # Skip if within this function
                        if pa >= func.start_addr and pa < func.end_addr:
                            continue
                        label_type = LabelType.Code
                        val -= 1
                    else:
                        label_type = LabelType.Data
                    label = self._get_label(val, label_type)
                    syms[val] = label
        return syms

    def _get_local(self, addr: int) -> str:
        if self.format_opts.branch_format == BranchFormat.ORDERED:
            idx = self.symbols.local_indexes[addr]
            prefix = "@@" if self.format_opts.prefixed_local else ""
            return f"{prefix}_{idx:03X}"
        else:
            return f"_{addr + ROM_OFFSET:08x}"

    def _get_label(self, addr: int, type: LabelType = LabelType.Undef) -> str:
        # Check for existing label
        if addr in self.symbols.globals:
            return self.symbols.globals[addr]
        # Check for code
        if addr % 4 == 1 and addr in self.symbols.thumb_code:
            return self.symbols.globals[addr - 1] + "+1"
        pa = addr - ROM_OFFSET
        if pa in self.symbols.locals:
            return self._get_local(pa)
        # Create label using addr
        label = f"{addr:X}"
        if type == LabelType.Imm:
            label = "0x" + label
        elif type == LabelType.Data:
            label = f"sUnk_{pa:x}"
        elif type == LabelType.Code:
            label = f"unk_{pa:x}"
        return label

    def _imm_str(self, instruct: ThumbInstruct) -> str:
        val = None
        if instruct.format in {
            ThumbForm.Shift,
            ThumbForm.AddSub,
            ThumbForm.Immed,
            ThumbForm.Swi
        }:
            val = instruct.imm
        elif instruct.format == ThumbForm.LdStI:
            if instruct.opcode < 2:
                val = instruct.imm * 4
            else:
                val = instruct.imm
        elif instruct.format == ThumbForm.LdStIH:
            val = instruct.imm * 2
        elif instruct.format == ThumbForm.LdStSP:
            val = instruct.imm * 4
        elif instruct.format == ThumbForm.RelAddr:
            assert instruct.rs == Reg.SP
            val = instruct.imm * 4
        elif instruct.format == ThumbForm.AddSP:
            val = instruct.imm * 4
            # Check if negative
            if instruct.opcode == 1:
                val = -val
        else:
            raise ValueError()
        prefix = "#" if self.format_opts.prefixed_immed else ""
        return prefix + self._hex_str(val)

    def _comma_join(self, items: list[str]) -> str:
        sep = ", " if self.format_opts.comma_space else ","
        return sep.join(items)

    def _rlist_str(self, instruct: ThumbInstruct) -> str:
        if self.format_opts.reg_list_range:
            runs = []
            prev = instruct.rlist[0]
            start = prev
            run = 1
            for reg in instruct.rlist[1:]:
                if reg == prev + 1:
                    run += 1
                else:
                    runs.append((start, run))
                    start = reg
                    run = 1
                prev = reg
            runs.append((start, run))
            reg_strs = []
            for start, run in runs:
                if run < 3:
                    for i in range(run):
                        reg_strs.append(f"r{start + i}")
                else:
                    reg_strs.append(f"r{start}-r{start + run - 1}")
        else:
            reg_strs = [f"r{n}" for n in instruct.rlist]
        result = self._comma_join(reg_strs)
        if self.format_opts.braced_reg_list:
            result = "{" + result + "}"
        return result

    def _hex_str(self, number: int) -> str:
        negative = number < 0
        number = abs(number)
        text = f"{number:X}"
        if number >= 0xA:
            text = "0x" + text
        if negative:
            text = "-" + text
        return text
