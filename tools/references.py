from typing import List
from rom import Rom, SIZE_32MB, ROM_OFFSET, ROM_END
from thumb import ThumbForm, ThumbInstruct


class References(object):

    def __init__(self, rom: Rom, addr: int):
        code_start = rom.code_start()
        code_end = rom.code_end()
        data_end = rom.data_end()

        # check if address has rom offset
        if addr >= ROM_OFFSET and addr < ROM_END:
            addr -= ROM_OFFSET

        # check if address is part of rom
        self.in_rom = False
        self.in_code = False
        if addr < SIZE_32MB:
            self.in_rom = True
            # check if address is part of code
            if addr >= code_start and addr < code_end:
                self.in_code = True

        self.bl_addrs = []
        self.ldr_addrs = []
        self.data_addrs = []

        # check bl and ldr in code
        addr_val = addr
        if self.in_rom:
            addr_val += ROM_OFFSET
            if self.in_code:
                addr_val += 1
        for i in range(code_start, code_end, 2):
            inst = ThumbInstruct(rom, i)
            if inst.format == ThumbForm.LdPC:
                val = rom.read32(inst.pc_rel_addr())
                if addr_val == val:
                    self.ldr_addrs.append(i)
            elif self.in_code and inst.format == ThumbForm.Link:
                if addr == inst.branch_addr():
                    self.bl_addrs.append(i)
        
        # check data
        for i in range(code_end, data_end, 4):
            val = rom.read32(i)
            if addr_val == val:
                self.data_addrs.append(i)

    def output(self) -> List[str]:
        lines = []

        if len(self.bl_addrs) > 0:
            lines.append("Function calls:")
            for addr in self.bl_addrs:
                lines.append(f"{addr:X}")

        if self.in_code and len(self.ldr_addrs) + len(self.data_addrs) > 0:
            lines.append("Function pointers:")

        if len(self.ldr_addrs) > 0:
            if not self.in_code:
                lines.append("Code:")
            for addr in self.ldr_addrs:
                lines.append(f"{addr:X}")

        if len(self.data_addrs) > 0:
            if not self.in_code:
                lines.append("Data:")
            for addr in self.data_addrs:
                lines.append(f"{addr:X}")
        
        if len(lines) == 0:
            lines = ["None found"]
        return lines



rom = Rom("/Users/labk/Desktop/mf_u.gba")
refs = References(rom, 0xB44)
lines = refs.output()
for line in lines:
    print(line)
