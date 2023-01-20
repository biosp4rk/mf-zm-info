import argparse
from typing import List
from rom import Rom, SIZE_32MB, ROM_OFFSET, ROM_END
import sys
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
        addr_type = None
        if self.in_rom:
            addr_type = "Code" if self.in_code else "Data"
        else:
            addr_type = "RAM"
        lines = [f"Type: {addr_type}", ""]

        num_bls = len(self.bl_addrs)
        if num_bls > 0:
            lines.append(f"Function calls ({num_bls}):")
            for addr in self.bl_addrs:
                lines.append(f"{addr:X}")
            lines.append("")

        num_ldrs = len(self.ldr_addrs)
        if num_ldrs > 0:
            lines.append(f"Pools ({num_ldrs}):")
            for addr in self.ldr_addrs:
                lines.append(f"{addr:X}")
            lines.append("")

        num_datas = len(self.data_addrs)
        if num_datas > 0:
            lines.append(f"Data ({num_datas}):")
            for addr in self.data_addrs:
                lines.append(f"{addr:X}")
            lines.append("")
            
        if num_bls + num_ldrs + num_datas == 0:
            lines.append("None found")
        return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_path", type=str)
    parser.add_argument("addr", type=str)
    args = parser.parse_args()

    if len(sys.argv) <= 2:
        parser.print_help()
        quit()
    # load rom
    rom = None
    try:
        rom = Rom(args.rom_path)
    except:
        print(f"Could not open rom at {args.rom_path}")
        quit()
    # get address
    addr = None
    try:
        addr = int(args.addr, 16)
    except:
        print(f"Invalid hex address {args.addr}")
        quit()
    # find references and print
    refs = References(rom, addr)
    lines = refs.output()
    for line in lines:
        print(line)
