import argparse
import sys
from typing import Dict, List

from constants import MAP_STRUCTS, MAP_CODE, MAP_DATA, MAP_RAM
from info_entry import StructEntry
from rom import Rom, SIZE_32MB, ROM_OFFSET, ROM_END
from thumb import ThumbForm, ThumbInstruct
from yaml_utils import load_yamls


class Ref(object):
    def __init__(self, addr, label=None, offset=None, index=None):
        self.addr = addr
        self.label = label
        self.index = index
        self.offset = offset

    def __str__(self) -> str:
        s = f"{self.addr:X}"
        if self.label is not None:
            s += f" {self.label}"
            if self.index is not None:
                s += f"[{self.index:X}]"
            if self.offset is not None:
                s += f":{self.offset:X}"
        return s


class References(object):

    def __init__(self, rom: Rom):
        self.rom = rom

    def find(self, addr: int):
        rom = self.rom
        code_start = rom.code_start()
        code_end = rom.code_end()
        data_end = rom.data_end()

        # check if address has rom offset
        if addr >= ROM_OFFSET and addr < ROM_END:
            addr -= ROM_OFFSET

        # check if address is part of rom
        in_rom = False
        in_code = False
        if addr < SIZE_32MB:
            in_rom = True
            # check if address is part of code
            if addr >= code_start and addr < code_end:
                in_code = True

        bl_addrs = []
        ldr_addrs = []
        data_addrs = []
        self.structs: Dict[str, StructEntry] = load_yamls(rom.game, MAP_STRUCTS)

        # check bl and ldr in code
        self.entries = load_yamls(rom.game, MAP_CODE, rom.region)
        self.idx = 0
        addr_val = addr
        if in_rom:
            addr_val += ROM_OFFSET
            if in_code:
                addr_val += 1
        for i in range(code_start, code_end, 2):
            inst = ThumbInstruct(rom, i)
            if inst.format == ThumbForm.LdPC:
                val = rom.read32(inst.pc_rel_addr())
                if addr_val == val:
                    ref = self.get_ref(i)
                    ldr_addrs.append(ref)
            elif in_code and inst.format == ThumbForm.Link:
                if addr == inst.branch_addr():
                    ref = self.get_ref(i)
                    bl_addrs.append(ref)

        # check data
        self.entries = load_yamls(rom.game, MAP_DATA, rom.region)
        self.idx = 0
        for i in range(code_end, data_end, 4):
            val = rom.read32(i)
            if addr_val == val:
                ref = self.get_ref(i)
                data_addrs.append(ref)
        
        return bl_addrs, ldr_addrs, data_addrs

    def find_all(self):
        # load all ram, code, data, and structs
        rom = self.rom
        ram_entries = load_yamls(rom.game, MAP_RAM, rom.region)
        code_entries = load_yamls(rom.game, MAP_CODE, rom.region)
        data_entries = load_yamls(rom.game, MAP_DATA, rom.region)
        #structs = read_yamls(rom.game, MAP_STRUCTS)

        # create dictionary of all labeled addresses
        combined = ram_entries + code_entries + data_entries
        all_refs = {entry["addr"]: entry for entry in combined}
        combined = None

        code_start = rom.code_start()
        code_end = rom.code_end()
        data_end = rom.data_end()

        # check every ref in code
        for i in range(code_start, code_end, 2):
            # check for bl
            inst = ThumbInstruct(rom, i)
            if inst.format == ThumbForm.Link:
                bl_addr = inst.branch_addr()
                self.check_ref(bl_addr, i, "bl", all_refs)
            # check for pool
            elif i % 4 == 0:
                self.check_addr(i, "pool", all_refs)

        # check every ref in data
        for i in range(code_end, data_end, 4):
            self.check_addr(i, "data", all_refs)
        
        results = {}
        for entry in all_refs.values():
            if "refs" in entry:
                label = entry["label"]
                results[label] = entry["refs"]
        return results

    def check_addr(self, addr, kind, refs):
        val = self.rom.read32(addr)
        if val >= self.rom.code_start(True) and val < self.rom.data_end(True):
            val -= ROM_OFFSET
            if val >= self.rom.code_start() and val < self.rom.code_end():
                # subtract one for thumb code pointers
                val -= 1
            self.check_ref(val, addr, kind, refs)

    def check_ref(self, val, addr, kind, refs):
        if val in refs:
            entry = refs[val]
            if "refs" not in entry:
                entry["refs"] = []
            entry["refs"].append((addr, kind))

    def get_ref(self, addr):
        while self.entries[self.idx].addr <= addr:
            self.idx += 1
        self.idx -= 1
        entry = self.entries[self.idx]
        length = entry.size(self.structs)
        count = entry.array_count()
        size = length // count
        if addr < entry.addr + length:
            lab = entry.label
            off = addr - entry.addr
            num = None
            if count > 1:
                num = off // size
                off %= size
            return Ref(addr, lab, off, num)
        return Ref(addr)


def output_section(title, refs) -> List[str]:
    lines = []
    num_refs = len(refs)
    if num_refs > 0:
        lines.append(f"{title} ({num_refs}):")
        for ref in refs:
            lines.append(str(ref))
        lines.append("")
    return lines


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_path", type=str)
    parser.add_argument("-o", "--addr", type=str)
    parser.add_argument("-a", "--all", action="store_true")
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
    refs = References(rom)

    if args.all:
        results = refs.find_all()
        for k, v in results.items():
            print(k + ":")
            for ad, ki in v:
                print(f"  {ad:X} {ki}")
    else:
        # get address
        addr = None
        try:
            addr = int(args.addr, 16)
        except:
            print(f"Invalid hex address {args.addr}")
            quit()
        # find references and print
        bls, ldrs, dats = refs.find(addr)
        lines = []
        if bls:
            lines += output_section("Calls", bls)
        if ldrs:
            lines += output_section("Pools", ldrs)
        if dats:
            lines += output_section("Data", dats)
        print("\n".join(lines))
