from typing import Dict, List, Set, Tuple
from constants import *
from function import Function
from rom import Rom, ROM_OFFSET
from utils import get_entry_size, read_yamls


class Pointers(object):
    def __init__(self, rom: Rom):
        self.rom = rom
        code = read_yamls(rom.game, MAP_CODE)
        self.code = get_sorted_region_entries(code, rom.region)
        data = read_yamls(rom.game, MAP_DATA)
        self.data = get_sorted_region_entries(data, rom.region)
        self.structs = read_yamls(rom.game, MAP_STRUCTS)

    def find_all_pointers(self) -> List[int]:
        # find all pointer locations in code and data
        locs = self.code_pointer_locs()
        locs += self.data_pointer_locs()

        # get sorted list of all locations and offsets
        all_ptrs = set(locs)
        for loc in locs:
            ptr = rom.read_ptr(loc)
            all_ptrs.add(ptr)
        all_ptrs = sorted(all_ptrs)

        # get labels for all pointers
        ptr_labels = {}
        code_end = self.rom.code_end()
        i = 0
        # code
        j = 0
        while True:
            ptr = all_ptrs[i]
            if ptr >= code_end:
                break
            i += 1
            # find nearest labeled code before curr addr
            j = get_next_entry_idx(self.code, j, ptr)
            entry = self.code[j]
            label = self.get_code_label(ptr, entry)
            ptr_labels[ptr] = label
        # data
        j = 0
        while i < len(all_ptrs):
            ptr = all_ptrs[i]
            i += 1
            # find nearest labeled data before curr addr
            j = get_next_entry_idx(self.data, j, ptr)
            entry = self.data[j]
            label = self.get_data_label(ptr, entry)
            ptr_labels[ptr] = label

        # print
        for ptr in locs:
            val = rom.read_ptr(ptr)
            lab1 = ptr_labels.get(ptr, "")
            lab2 = ptr_labels.get(val, "")
            print(f"{ptr:X}\t{val:X}\t{lab1}\t{lab2}")
        return locs


    def code_pointer_locs(self) -> List[int]:
        func_addr = self.rom.code_start()
        code_end = self.rom.code_end()
        rom_start = self.rom.code_start(True)
        rom_end = self.rom.data_end(True)
        arm_funcs = self.rom.arm_functions()
        # go through each function
        locs = []
        while func_addr < code_end:
            # skip arm functions
            if func_addr in arm_funcs:
                func_addr = arm_funcs[func_addr]
                continue
            # disassemble function and check pools
            func = Function(self.rom, func_addr)
            pools = func.get_data_pools()
            for addr, size in pools:
                for i in range(0, size, 4):
                    loc = addr + i
                    val = self.rom.read32(loc)
                    # check if in range to be pointer
                    if val >= rom_start and val < rom_end:
                        locs.append(loc)
            func_addr = func.end_addr
        return locs

    def data_pointer_locs(self) -> List[int]:
        rom_start = self.rom.code_start(True)
        rom_end = self.rom.data_end(True)
        # find all pointers in data
        locs = []
        i = 0
        data_start = self.rom.data_start()
        data_end = self.rom.data_end()
        for data_addr in range(data_start, data_end, 4):
            val = self.rom.read32(data_addr)
            # check if in range to be pointer
            if val < rom_start or val >= rom_end:
                continue
            # find nearest data entry
            i = get_next_entry_idx(self.data, i, data_addr)
            if i != -1:
                entry = self.data[i]
                if not self.check_data_addr(data_addr, entry):
                    continue
            locs.append(data_addr)
        return locs

    def check_data_addr(self, addr: int, entry) -> bool:
        # check if address falls within entry
        size = get_entry_size(entry, self.structs)[rom.region]
        entry_addr = entry["addr"]
        end = entry_addr + size
        if addr >= end:
            # not part of entry
            return True
        t = entry.get("type")
        if t is None:
            # type isn't known
            return True
        t = t.split(".")[0]
        offset = addr - entry_addr
        if t in self.structs:
            if t == "PcmSample" and addr > entry_addr:
                return False
            # check if struct variable at offset is defined
            struct = self.structs[t]
            # get entry index and struct offset
            offset %= struct["size"]
            vars = [v for v in struct["vars"] if v["offset"] == offset]
            if len(vars) > 0:
                assert len(vars) == 1
                vt = vars[0]["type"].split(".")[0]
                if vt != "ptr":
                    return False
        else:
            assert t in PRIMITIVES
            if t != "ptr":
                # any non-pointer primitive cannot contain pointers
                return False
        return True

    def get_code_label(self, addr: int, entry) -> str:
        size = entry["size"]
        if isinstance(size, dict):
            size = size[rom.region]
        if addr >= entry["addr"] + size:
            return ""
        off = addr - entry["addr"]
        return entry["label"] + f"[{off:X}]"

    def get_data_label(self, addr: int, entry) -> str:
        # check if address falls within entry
        size = get_entry_size(entry, self.structs)[rom.region]
        entry_addr = entry["addr"]
        end = entry_addr + size
        if addr >= end:
            return ""
        t = entry.get("type")
        if t is None:
            return ""
        t = t.split(".")[0]
        # get entry index and struct offset
        size = None
        idx = 0
        offset = addr - entry_addr
        if t in self.structs:
            size = self.structs[t]["size"]
        elif t == "ptr":
            size = 4
        if size:
            idx = offset // size
            offset %= size
        # construct label
        label = entry["label"]
        if idx > 0 or offset > 0:
            label += f"[{idx:X}]"
            if offset > 0:
                label += f"[{offset:X}]"
        return label


def get_sorted_region_entries(entries: List, region: str):
    entries = [x for x in entries if region in x["addr"]]
    for x in entries:
        x["addr"] = x["addr"][region]
    return sorted(entries, key=lambda x: x["addr"])


def get_next_entry_idx(entries: List, idx: int, addr: int) -> int:
    # find nearest labeled data before curr addr
    while entries[idx]["addr"] <= addr:
        idx += 1
        if idx == len(entries):
            return -1
    return idx - 1



rom = Rom("C:\\Users\\kwlab\\Desktop\\gbamet\\mf_u.gba")
ptrs = Pointers(rom)
pls = ptrs.find_all_pointers()
