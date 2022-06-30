from typing import Dict, List, Set, Tuple
from constants import *
from function import Function
from rom import Rom, ROM_OFFSET
from utils import get_entry_size, read_yamls


def find_all_pointers(rom: Rom) -> List[int]:
    ptr_locs: List[int] = []
    ptrs: Set[int] = set()
    ptr_labels: Dict[int, str] = {}

    # find all pointers in functions
    func_addr = rom.code_start()
    code_end = rom.code_end()
    rom_start = rom.code_start(True)
    rom_end = rom.data_end(True)
    arm_funcs = rom.arm_functions()
    while func_addr < code_end:
        # skip arm functions
        if func_addr in arm_funcs:
            func_addr = arm_funcs[func_addr]
            continue
        # disassemble function and check pools
        func = Function(rom, func_addr)
        pools = func.get_data_pools()
        for addr, size in pools:
            for i in range(0, size, 4):
                loc = addr + i
                val = rom.read32(loc)
                # check if in range to be pointer
                if val >= rom_start and val < rom_end:
                    ptr_locs.append(loc)
                    ptrs.add(val - ROM_OFFSET)
        func_addr = func.end_addr

    # get data and structs
    data = read_yamls(rom.game, MAP_DATA)
    structs = read_yamls(rom.game, MAP_STRUCTS)
    # filter entries by region
    data = get_sorted_region_entries(data, rom.region)
    data.append({"addr": 0xFFFFFFFF})

    # find all pointers in data
    data_start = rom.data_start()
    data_end = rom.data_end()
    for data_addr in range(data_start, data_end, 4):
        val = rom.read32(data_addr)
        # check if in range to be pointer
        if val < rom_start or val >= rom_end:
            continue
        ptr_locs.append(data_addr)
        ptrs.add(val - ROM_OFFSET)

    # get labels for all pointers
    all_ptrs = sorted(set(ptr_locs) | ptrs)
    valid_ptrs = set()
    ptr_idx = 0
    # code
    code = read_yamls(rom.game, MAP_CODE)
    code = get_sorted_region_entries(code, rom.region)
    entry_idx = 0
    while True:
        ptr = all_ptrs[ptr_idx]
        if ptr >= code_end:
            break
        ptr_idx += 1
        # find nearest labeled code before curr addr
        entry, entry_idx = get_next_entry(code, entry_idx, ptr)
        size = entry["size"]
        if isinstance(size, dict):
            size = size[rom.region]
        label = ""
        if ptr < entry["addr"] + size:    
            off = ptr - entry["addr"]
            label = entry["label"] + f"[{off:X}]"
        ptr_labels[ptr] = label
        valid_ptrs.add(ptr)
    # data
    entry_idx = 0
    while ptr_idx < len(all_ptrs):
        ptr = all_ptrs[ptr_idx]
        ptr_idx += 1
        # find nearest labeled data before curr addr
        entry, entry_idx = get_next_entry(data, entry_idx, ptr)
        label = check_addr_in_entry(ptr, entry, structs, rom)
        if label is None:
            continue
        ptr_labels[ptr] = label
        valid_ptrs.add(ptr)

    ptr_locs = [p for p in ptr_locs if p in valid_ptrs]
    for ptr in ptr_locs:
        val = rom.read_ptr(ptr)
        lab1 = ptr_labels.get(ptr, "")
        lab2 = ptr_labels.get(val, "")
        print(f"{ptr:X}\t{val:X}\t{lab1}\t{lab2}")
    return ptr_locs


def get_sorted_region_entries(entries: List, region: str):
    entries = [x for x in entries if region in x["addr"]]
    for x in entries:
        x["addr"] = x["addr"][region]
    return sorted(entries, key=lambda x: x["addr"])


def get_next_entry(entries: List, idx: int, addr: int):
    # find nearest labeled data before curr addr
    while entries[idx]["addr"] <= addr:
        idx += 1
        if idx == len(entries):
            return None, idx
    idx -= 1
    return entries[idx], idx


def check_addr_in_entry(addr: int, entry, structs, rom: Rom):
    label: str = ""
    size = get_entry_size(entry, structs)[rom.region]
    # check if address falls within entry
    if addr < entry["addr"] + size and entry.get("type") is not None:
        t = entry["type"].split(".")[0]
        if t in structs:
            if t == "PcmSample" and addr > entry["addr"]:
                return None
            # check if struct variable at offset is defined
            struct = structs[t]
            # get entry index and struct offset
            offset = addr - entry["addr"]
            entry_idx = offset // struct["size"]
            offset %= struct["size"]
            label = entry["label"] + f"[{entry_idx:X}][{offset:X}]"
            vars = [v for v in struct["vars"] if v["offset"] == offset]
            if len(vars) > 0:
                assert len(vars) == 1
                vt = vars[0]["type"].split(".")[0]
                if vt != "ptr":
                    return None
        elif t != "ptr":
            # any non-pointer primitive cannot contain pointers
            assert t in PRIMITIVES
            return None
    return label


rom = Rom("C:\\Users\\kwlab\\Desktop\\gbamet\\mf_u.gba")
pls = find_all_pointers(rom)
