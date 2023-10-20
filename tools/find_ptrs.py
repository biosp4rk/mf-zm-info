import argparse
from enum import Enum
from typing import Any, Dict, List, Tuple, Union

import argparse_utils as apu
from constants import *
from function import Function
from game_info import GameInfo
from info_entry import PrimType, InfoEntry, DataEntry, StructEntry, StructVarEntry
from rom import Rom, ROM_OFFSET


class Validity(Enum):
    Unknown = 0
    Invalid = 1
    Valid = 2


def find_nearest_entry(entries: List[InfoEntry], addr: int) -> InfoEntry:
    left = 0
    right = len(entries) - 1
    mid: int = -1
    while left <= right:
        mid = (left + right) // 2
        if entries[mid].addr < addr:
            left = mid + 1
        elif entries[mid].addr > addr:
            right = mid - 1
        else:
            break
    return entries[mid]


def get_refs_in_code(
    rom: Rom,
    refs: Dict[int, List[int]]
) -> None:
    addr = rom.code_start()
    code_end = rom.code_end()
    v_code_start = rom.code_start(True)
    v_data_end = rom.data_end(True)
    arm_funcs = rom.arm_functions()
    while addr < code_end:
        if addr in arm_funcs:
            addr = arm_funcs[addr]
        else:
            func = Function(rom, addr)
            for loc in func.data_pool:
                val = rom.read32(loc)
                if val >= v_code_start and val < v_data_end:
                    val -= ROM_OFFSET
                    if val in refs:
                        refs[val].append(loc)
                    else:
                        refs[val] = [loc]
            addr = func.end_addr


def find_all_assets(rom: Rom):
    info = GameInfo(rom.game, rom.region, True)
    code_set = set(c.addr for c in info.code)
    data_list = info.data

    refs: Dict[int, List[int]] = {}
    for entry in data_list:
        refs[entry.addr] = []
    get_refs_in_code(rom, refs)

    code_start = rom.code_start()
    code_end = rom.code_end()
    data_start = rom.data_start()
    data_end = rom.data_end()
    v_code_start = rom.code_start(True)
    v_data_end = rom.data_end(True)

    idx = 0

    for addr in range(data_start, data_end, 4):
        # check if addr could contain a ptr
        val = rom.read32(addr)
        if val < v_code_start or val >= v_data_end:
            continue
        val -= ROM_OFFSET
        # check if this address falls within a known asset
        valid = Validity.Unknown
        msg = ""
        idx, entry, _, _ = find_prim_at_offset(data_list, idx, addr, info)
        if entry:
            lab = data_list[idx].label
            data_addr = data_list[idx].addr
            text = f"{data_addr:X} {lab}"
            if data_addr % 4 != 0:
                valid = Validity.Invalid
                msg = f"loc entry not aligned {text}"
            elif not entry.is_ptr():
                valid = Validity.Invalid
                msg = f"loc entry not ptr {text}"
            else:
                valid = Validity.Valid
                msg = f"loc entry {text}"
        
        # check if the pointer falls within a known asset
        if valid == Validity.Unknown and val >= code_start and val < data_end:
            if val < code_end:
                # subtract one for thumb code pointers
                val -= 1
                if val not in code_set:
                    valid = Validity.Invalid
                    msg = "bad code ptr"
                else:
                    msg = "code ptr"
            else:
                j, entry, prim_idx, prim_off = find_prim_at_offset(data_list, 0, val, info)
                if entry:
                    lab = data_list[j].label
                    data_addr = data_list[j].addr
                    text = f"{data_addr:X} {lab}"
                    if prim_idx != 0 or prim_off != 0:
                        valid = Validity.Invalid
                        msg = f"points to middle {text}"
                    else:
                        msg = f"val entry {text}"
        # add ref
        if valid != Validity.Invalid:
            if val in refs:
                refs[val].append(addr)
            else:
                refs[val] = [addr]
        # print
        valid_str = "unk"
        if valid == Validity.Invalid:
            valid_str = "no"
        elif valid == Validity.Valid:
            valid_str = "yes"
        print(f"{addr:X}\t{val:06X}\t{valid_str}\t{msg}")

    with open("_syms.txt", "w") as f:
        for addr in sorted(refs.keys()):
            #ptrs = refs[addr]
            #ptr_str = ",".join(f"{p:X}" for p in ptrs)
            f.write(f"{addr:06X}\n")


def find_prim_at_offset(
    entries: Union[List[DataEntry], List[StructVarEntry]],
    idx: int,
    offset: int,
    info: GameInfo
) -> Tuple[int, Union[DataEntry, StructEntry], int, int]:
    # returns idx, entry, prim_num, prim_offset
    if len(entries) == 0:
        return (idx, None, None, None)
    off_attr = "offset" if isinstance(entries[0], StructVarEntry) else "addr"
    while idx < len(entries) and getattr(entries[idx], off_attr) <= offset:
        idx += 1
    idx -= 1
    entry = entries[idx]
    # check if address within entry
    entry_off = getattr(entry, off_attr)
    length = entry.get_size(info.structs)
    if offset < entry_off + length:
        # get offset within single item
        off = offset - entry_off
        num = 0
        count = entry.get_count()
        if count > 1:
            size = length // count
            num = off // size
            off %= size
        # check type
        is_ptr = entry.is_ptr()
        if not is_ptr and entry.primitive == PrimType.Struct:
            # check primitive at offset
            s_entry = info.get_struct(entry.struct_name)
            _, entry, num, off = find_prim_at_offset(s_entry.vars, 0, off, info)
        return (idx, entry, num, off)
    return (idx, None, None, None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)

    args = parser.parse_args()
    rom = Rom(args.rom_path)

    find_all_assets(rom)
