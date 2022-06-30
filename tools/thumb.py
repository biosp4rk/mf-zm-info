from enum import Enum
from typing import List
from rom import Rom, ROM_OFFSET


class ThumbForm(Enum):
    Undef = 0
    Shift = 1
    AddSub = 2
    Immed = 3
    AluOp = 4
    HiReg = 5
    LdPC = 6
    LdStR = 7
    LdStRS = 8
    LdStI = 9
    LdStIH = 10
    LdStSP = 11
    RelAddr = 12
    AddSP = 13
    PushPop = 14
    LdStM = 15
    CondB = 16
    Swi = 17
    UncondB = 18
    Link = 19


class ThumbOp(Enum):
    Undef = 0
    # logical operations
    MOV = 1
    MVN = 2
    AND = 3
    TST = 4
    BIC = 5
    ORR = 6
    EOR = 7
    LSL = 8
    LSR = 9
    ASR = 10
    ROR = 11
    NOP = 12
    # arithmetic operations
    ADD = 13
    ADC = 14
    SUB = 15
    SBC = 16
    NEG = 17
    CMP = 18
    CMN = 19
    MUL = 20
    # jumps and calls
    B = 21
    BEQ = 22
    BNE = 23
    BCS = 24
    BCC = 25
    BMI = 26
    BPL = 27
    BVS = 28
    BVC = 29
    BHI = 30
    BLS = 31
    BGE = 32
    BLT = 33
    BGT = 34
    BLE = 35
    BL = 36
    BX = 37
    SWI = 38
    BKPT = 39
    BLX = 40
    # memory load/store
    LDR = 41
    LDRB = 42
    LDRH = 43
    LDSB = 44
    LDSH = 45
    STR = 46
    STRB = 47
    STRH = 48
    PUSH = 49
    POP = 50
    LDMIA = 51
    STMIA = 52


class ThumbInstruct(object):
    phys_addr: int
    format: ThumbForm
    opcode: int
    opname: ThumbOp
    rd: int
    # use Rs for Rb
    rs: int
    rn: int
    ro: int
    rlist: List[int]
    imm: int

    def __init__(self, rom: Rom, addr: int):
        self.phys_addr = addr
        val = rom.read16(addr)
        self.set_format(val)
        self.set_opcode(val)
        self.set_rd(val)
        self.set_rs(val)
        self.set_rn(val)
        self.set_ro(val)
        self.set_rlist(val)
        if self.format == ThumbForm.Link:
            val2 = rom.read16(addr + 2)
            self.imm = ((val & 2047) << 11) | (val2 & 2047)
        else:
            self.set_imm(val)
        self.set_opname()

    def __str__(self) -> str:
        fields = [
            f"OpCode={self.opname}",
            f"Format={self.format}"
        ]
        if self.rd is not None:
            fields.append(f"Rd={self.rd}")
        if self.rs is not None:
            fields.append(f"Rs={self.rs}")
        if self.rn is not None:
            fields.append(f"Rn={self.rn}")
        if self.ro is not None:
            fields.append(f"Ro={self.ro}")
        if self.rlist is not None:
            regs = ", ".join(str(r) for r in self.rlist)
            fields.append(f"Rlist=[{regs}]")
        if self.imm is not None:
            fields.append(f"Imm={self.imm}");
        return ", ".join(fields)

    def set_format(self, val: int) -> None:
        bits_13_15 = val >> 13
        if bits_13_15 == 0:
            self.format = ThumbForm.AddSub if (val >> 11 & 3) == 3 else ThumbForm.Shift
        elif bits_13_15 == 1:
            self.format = ThumbForm.Immed
        elif bits_13_15 == 2:
            if val >> 12 & 1:
                self.format = ThumbForm.LdStRS if val >> 9 & 1 else ThumbForm.LdStR
            else:
                if val >> 11 & 1:
                    self.format = ThumbForm.LdPC
                else:
                    self.format = ThumbForm.HiReg if val >> 10 & 1 else ThumbForm.AluOp
        elif bits_13_15 == 3:
            self.format = ThumbForm.LdStI
        elif bits_13_15 == 4:
            self.format = ThumbForm.LdStSP if val >> 12 & 1 else ThumbForm.LdStIH
        elif bits_13_15 == 5:
            if val >> 12 & 1:
                b = val >> 8 & 15
                if b == 0:
                    self.format = ThumbForm.AddSP
                # BKPT
                elif b == 14:
                    self.format = ThumbForm.Undef
                else:
                    self.format = ThumbForm.PushPop
            else:
                self.format = ThumbForm.RelAddr
        elif bits_13_15 == 6:
            if val >> 12 & 1:
                cond = val >> 8 & 15
                if cond == 14:
                    self.format = ThumbForm.Undef
                elif cond == 15:
                    self.format = ThumbForm.Swi
                else:
                    self.format = ThumbForm.CondB
            else:
                self.format = ThumbForm.LdStM
        elif bits_13_15 == 7:
            self.format = ThumbForm.Link if val >> 12 & 1 else ThumbForm.UncondB

    def set_opcode(self, val: int) -> None:
        self.opcode = 0
        if self.format in {
            ThumbForm.Shift, ThumbForm.Immed, ThumbForm.LdStI
        }:
            self.opcode = val >> 11 & 3
        elif self.format == ThumbForm.AddSub:
            self.opcode = val >> 9 & 3
        elif self.format == ThumbForm.AluOp:
            self.opcode = val >> 6 & 15
        elif self.format == ThumbForm.HiReg:
            self.opcode = val >> 8 & 3
        elif self.format == ThumbForm.LdPC:
            self.opcode = val >> 8 & 7
        elif self.format in {ThumbForm.LdStR, ThumbForm.LdStRS}:
            self.opcode = val >> 9 & 3
        elif self.format in {
            ThumbForm.LdStIH,
            ThumbForm.LdStSP,
            ThumbForm.RelAddr,
            ThumbForm.PushPop,
            ThumbForm.LdStM
        }:
            self.opcode = val >> 11 & 1
        elif self.format == ThumbForm.AddSP:
            self.opcode = val >> 7 & 1
        elif self.format == ThumbForm.CondB:
            self.opcode = val >> 8 & 15

    def set_rd(self, val: int) -> None:
        self.rd: int = None
        if self.format in {
            ThumbForm.Shift,
            ThumbForm.AddSub,
            ThumbForm.AluOp,
            ThumbForm.LdStR,
            ThumbForm.LdStRS,
            ThumbForm.LdStI,
            ThumbForm.LdStIH
        }:
            self.rd = val & 7
        elif self.format in {
            ThumbForm.Immed,
            ThumbForm.LdPC,
            ThumbForm.LdStSP,
            ThumbForm.RelAddr,
            ThumbForm.LdStM
        }:
            self.rd = val >> 8 & 7
        elif self.format == ThumbForm.HiReg:
            self.rd = ((val & 0x80) >> 4) | (val & 7)

    def set_rs(self, val: int) -> None:
        self.rs: int = None
        if self.format in {
            ThumbForm.Shift,
            ThumbForm.AddSub,
            ThumbForm.Immed,
            ThumbForm.AluOp,
            ThumbForm.LdStR,
            ThumbForm.LdStRS,
            ThumbForm.LdStI,
            ThumbForm.LdStIH
        }:
            self.rs = val >> 3 & 7
        elif self.format == ThumbForm.HiReg:
            self.rs = val >> 3 & 15

    def set_rn(self, val: int) -> None:
        self.rn: int = None
        if self.format == ThumbForm.AddSub and self.opcode < 2:
            self.rn = val >> 6 & 7

    def set_ro(self, val: int) -> None:
        self.ro: int = None
        if self.format == ThumbForm.LdStR or self.format == ThumbForm.LdStRS:
            self.ro = val >> 6 & 7

    def set_rlist(self, val: int) -> None:
        self.rlist: List[int] = None
        if self.format == ThumbForm.PushPop or self.format == ThumbForm.LdStM:
            self.rlist = [r for r in range(8) if val >> r & 1]
            if self.format == ThumbForm.PushPop and (val & 0x100):
                if self.opcode == 0:
                    self.rlist.append(14)
                else:
                    self.rlist.append(15)

    def set_imm(self, val: int) -> None:
        self.imm: int = None
        if self.format in {
            ThumbForm.Shift,
            ThumbForm.LdStI,
            ThumbForm.LdStIH
        }:
            self.imm = val >> 6 & 31
        elif self.format == ThumbForm.AddSub:
            if self.opcode >= 2:
                self.imm = val >> 6 & 7
        elif self.format in {
            ThumbForm.Immed,
            ThumbForm.LdPC,
            ThumbForm.LdStSP,
            ThumbForm.RelAddr,
            ThumbForm.AddSP,
            ThumbForm.CondB,
            ThumbForm.Swi
        }:
            self.imm = val & 255
        elif self.format == ThumbForm.UncondB:
            self.imm = val & 1023
        elif self.format == ThumbForm.Link:
            raise ValueError("Set in constructor")

    def set_opname(self) -> None:
        self.opname: ThumbOp = None
        if self.format == ThumbForm.Shift:
            if self.opcode == 0:
                self.opname = ThumbOp.LSL
            elif self.opcode == 1:
                self.opname = ThumbOp.LSR
            elif self.opcode == 2:
                self.opname = ThumbOp.ASR
        elif self.format == ThumbForm.AddSub:
            if self.opcode == 0:
                self.opname = ThumbOp.ADD
            elif self.opcode == 1:
                self.opname = ThumbOp.SUB
            elif self.opcode == 2:
                self.opname = ThumbOp.MOV if self.imm == 0 else ThumbOp.ADD
            elif self.opcode == 3:
                self.opname = ThumbOp.ASR
        elif self.format == ThumbForm.Immed:
            if self.opcode == 0:
                self.opname = ThumbOp.MOV
            elif self.opcode == 1:
                self.opname = ThumbOp.CMP
            elif self.opcode == 2:
                self.opname = ThumbOp.ADD
            elif self.opcode == 3:
                self.opname = ThumbOp.SUB
        elif self.format == ThumbForm.AluOp:
            if self.opcode == 0:
                self.opname = ThumbOp.AND
            elif self.opcode == 1:
                self.opname = ThumbOp.EOR
            elif self.opcode == 2:
                self.opname = ThumbOp.LSL
            elif self.opcode == 3:
                self.opname = ThumbOp.LSR
            elif self.opcode == 4:
                self.opname = ThumbOp.ASR
            elif self.opcode == 5:
                self.opname = ThumbOp.ADC
            elif self.opcode == 6:
                self.opname = ThumbOp.SBC
            elif self.opcode == 7:
                self.opname = ThumbOp.ROR
            elif self.opcode == 8:
                self.opname = ThumbOp.TST
            elif self.opcode == 9:
                self.opname = ThumbOp.NEG
            elif self.opcode == 10:
                self.opname = ThumbOp.CMP
            elif self.opcode == 11:
                self.opname = ThumbOp.CMN
            elif self.opcode == 12:
                self.opname = ThumbOp.ORR
            elif self.opcode == 13:
                self.opname = ThumbOp.MUL
            elif self.opcode == 14:
                self.opname = ThumbOp.BIC
            elif self.opcode == 15:
                self.opname = ThumbOp.MVN
        elif self.format == ThumbForm.HiReg:
            if self.opcode == 0:
                self.opname = ThumbOp.ADD
            elif self.opcode == 1:
                self.opname = ThumbOp.CMP
            elif self.opcode == 2:
                self.opname = ThumbOp.NOP if self.rd == 8 and self.rs == 8 else ThumbOp.MOV
            elif self.opcode == 3:
                self.opname = ThumbOp.BX
        elif self.format == ThumbForm.LdPC:
            self.opname = ThumbOp.LDR
        elif self.format == ThumbForm.LdStR:
            if self.opcode == 0:
                self.opname = ThumbOp.STR
            elif self.opcode == 1:
                self.opname = ThumbOp.STRB
            elif self.opcode == 2:
                self.opname = ThumbOp.LDR
            elif self.opcode == 3:
                self.opname = ThumbOp.LDRB
        elif self.format == ThumbForm.LdStRS:
            if self.opcode == 0:
                self.opname = ThumbOp.STRH
            elif self.opcode == 1:
                self.opname = ThumbOp.LDSB
            elif self.opcode == 2:
                self.opname = ThumbOp.LDRH
            elif self.opcode == 3:
                self.opname = ThumbOp.LDSH
        elif self.format == ThumbForm.LdStI:
            if self.opcode == 0:
                self.opname = ThumbOp.STR
            elif self.opcode == 1:
                self.opname = ThumbOp.LDR
            elif self.opcode == 2:
                self.opname = ThumbOp.STRB
            elif self.opcode == 3:
                self.opname = ThumbOp.LDRB
        elif self.format == ThumbForm.LdStIH:
            self.opname = ThumbOp.STRH if self.opcode == 0 else ThumbOp.LDRH
        elif self.format == ThumbForm.LdStSP:
            self.opname = ThumbOp.STR if self.opcode == 0 else ThumbOp.LDR
        elif (self.format == ThumbForm.RelAddr or
            self.format == ThumbForm.AddSP):
            self.opname = ThumbOp.ADD
        elif self.format == ThumbForm.PushPop:
            self.opname = ThumbOp.PUSH if self.opcode == 0 else ThumbOp.POP
        elif self.format == ThumbForm.LdStM:
            self.opname = ThumbOp.STMIA if self.opcode == 0 else ThumbOp.LDMIA
        elif self.format == ThumbForm.CondB:
            if self.opcode == 0:
                self.opname = ThumbOp.BEQ
            elif self.opcode == 1:
                self.opname = ThumbOp.BNE
            elif self.opcode == 2:
                self.opname = ThumbOp.BCS
            elif self.opcode == 3:
                self.opname = ThumbOp.BCC
            elif self.opcode == 4:
                self.opname = ThumbOp.BMI
            elif self.opcode == 5:
                self.opname = ThumbOp.BPL
            elif self.opcode == 6:
                self.opname = ThumbOp.BVS
            elif self.opcode == 7:
                self.opname = ThumbOp.BVC
            elif self.opcode == 8:
                self.opname = ThumbOp.BHI
            elif self.opcode == 9:
                self.opname = ThumbOp.BLS
            elif self.opcode == 10:
                self.opname = ThumbOp.BGE
            elif self.opcode == 11:
                self.opname = ThumbOp.BLT
            elif self.opcode == 12:
                self.opname = ThumbOp.BGT
            elif self.opcode == 13:
                self.opname = ThumbOp.BLE
        elif self.format == ThumbForm.Swi:
            self.opname = ThumbOp.SWI
        elif self.format == ThumbForm.UncondB:
            self.opname = ThumbOp.B
        elif self.format == ThumbForm.Link:
            self.opname = ThumbOp.BL

    def virt_addr(self) -> int:
        return self.phys_addr + ROM_OFFSET

    def branch_addr(self) -> int:
        off = self.imm * 2
        if self.format == ThumbForm.CondB:
            if off >= 256:
                off -= 4096
        elif self.format == ThumbForm.UncondB:
            if off >= 2048:
                off -= 4096
        elif self.format == ThumbForm.Link:
            if off >= 0x400000:
                off -= 0x800000
        else:
            raise ValueError()
        return self.phys_addr + 4 + off

    def pc_rel_addr(self) -> int:
        if (self.format != ThumbForm.LdPC and
            self.format != ThumbForm.RelAddr):
            raise ValueError()
        pc = (self.phys_addr + 4) & ~2
        return pc + self.imm * 4

    def rlist_bits(self) -> int:
        if (self.format != ThumbForm.PushPop and
            self.format != ThumbForm.LdStM):
            raise ValueError()  
        regs = 0
        for reg in self.rlist:
            if reg <= 7:
                regs |= 1 << reg
            elif ((reg == 14 and self.opname == ThumbOp.PUSH) or
                (reg == 15 and self.opname == ThumbOp.POP)):
                regs |= 0x100
            else:
                raise ValueError()
        return regs
