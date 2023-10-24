import argparse
from enum import Enum
from typing import List, Tuple, Union

import argparse_utils as apu
from constants import *
from function import Function
from game_info import GameInfo
from info_entry import PrimType, DataEntry, StructEntry, StructVarEntry
from rom import Rom, ROM_OFFSET


class Validity(Enum):
    Unknown = 0
    Invalid = 1
    Valid = 2


def find_code_ptrs(rom: Rom) -> List[int]:
    addr = rom.code_start()
    code_end = rom.code_end()
    v_code_start = rom.code_start(True)
    v_data_end = rom.data_end(True)
    arm_funcs = rom.arm_functions()
    ptr_locs: List[int] = []
    while addr < code_end:
        if addr in arm_funcs:
            addr = arm_funcs[addr]
            continue
        func = Function(rom, addr)
        ptr_locs += func.get_jump_tables()
        for loc in func.data_pool:
            val = rom.read32(loc)
            # check if value falls within rom
            if val >= v_code_start and val < v_data_end:
                ptr_locs.append(loc)
        addr = func.end_addr
    ptr_locs.sort()
    return ptr_locs


def find_sound_header_ptrs(rom: Rom, info: GameInfo) -> List[int]:
    sound_entries = info.get_data("SoundDataEntries")
    se_addr = sound_entries.addr
    count = sound_entries.arr_count
    size = info.get_struct(sound_entries.struct_name).size
    ptr_locs: List[int] = []
    for idx in range(count):
        addr = rom.read_ptr(se_addr + (idx * size))
        num_tracks = rom.read8(addr)
        if num_tracks == 0:
            continue
        ptr_locs.append(addr + 4)
        for j in range(num_tracks):
            ptr_locs.append(addr + 8 + (j * 4))
    ptr_locs.sort()
    return ptr_locs


def get_track_start_end(rom: Rom) -> Tuple[int, int]:
    addrs = None
    if rom.game == GAME_MF:
        if rom.region == REGION_U:
            addrs = (0x25895C, 0x289960)
    if addrs is None:
        raise NotImplementedError()
    return addrs


def find_track_ptrs(rom: Rom):
    start, end = get_track_start_end(rom)
    v_start = start + ROM_OFFSET
    v_end = end + ROM_OFFSET
    ptr_locs: List[int] = []
    for addr in range(start, end):
        val = rom.read8(addr)
        if val != 0xB2 and val != 0xB3:
            continue
        addr += 1
        val = rom.read32(addr)
        if val < v_start or val >= v_end:
            continue
        val -= ROM_OFFSET
        if val >= addr:
            continue
        ptr_locs.append(addr)
    return ptr_locs


def find_data_ptrs(rom: Rom, info: GameInfo) -> List[int]:
    code_dict = {c.addr: c.label for c in info.code}
    data_list = info.data

    code_end = rom.code_end()
    data_start = rom.data_start()
    data_end = rom.data_end()
    v_code_start = rom.code_start(True)
    v_data_end = rom.data_end(True)

    idx = 0
    prev_addr = 0
    ptr_locs: List[int] = []

    for addr in range(data_start, data_end, 4):
        # check if value at address falls within rom
        val = rom.read32(addr)
        if val < v_code_start or val >= v_data_end:
            continue
        val -= ROM_OFFSET
        # check if this address falls within a known asset
        valid = Validity.Unknown
        msg = "?"
        idx, entry, _, _ = find_prim_at_offset(data_list, idx, addr, info)
        if entry:
            data_entry = data_list[idx]
            data_addr = data_entry.addr
            text = f"{data_addr:X} {data_entry.label}"
            if data_addr % 4 != 0:
                valid = Validity.Invalid
                msg = f"X loc entry not aligned {text}"
            elif not entry.is_ptr():
                valid = Validity.Invalid
                msg = f"X loc entry not ptr {text}"
            else:
                valid = Validity.Valid
                msg = f"O loc entry {text}"
        
        # check if the value points to known asset
        if valid == Validity.Unknown:
            if val < code_end:
                # check if value points to code
                # subtract one for thumb code pointers
                val -= 1
                if val not in code_dict:
                    valid = Validity.Invalid
                    msg = "X ptr code middle"
                else:
                    label = code_dict[val]
                    msg = f"O ptr code {label}"
            else:
                # check if value points to known data
                j, entry, prim_idx, prim_off = find_prim_at_offset(data_list, 0, val, info)
                if entry:
                    data_entry = data_list[j]
                    data_addr = data_entry.addr
                    text = f"{data_addr:X} {data_entry.label}"
                    if prim_idx != 0 or prim_off != 0:
                        valid = Validity.Invalid
                        msg = f"X ptr data middle {text}"
                    else:
                        msg = f"O ptr data {text}"
        # print
        # valid_str = "unk"
        # if valid == Validity.Invalid:
        #     valid_str = "no"
        # elif valid == Validity.Valid:
        #     valid_str = "yes"
        # diff = addr - prev_addr
        # print(f"{addr:X}\t{val:06X}\t{diff:X}\t{valid_str}\t{msg}")
        if valid != Validity.Invalid:
            ptr_locs.append(addr)
        prev_addr = addr
    return ptr_locs


def find_prim_at_offset(
    entries: Union[List[DataEntry], List[StructVarEntry]],
    idx: int,
    offset: int,
    info: GameInfo
) -> Tuple[int, Union[DataEntry, StructEntry], int, int]:
    """
    Tries to find the primitive at the provided address (for data entries)
    or offset (for struct var entries).
    Returns (index, entry, prim_num, prim_offset).
    """
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
    rom = apu.get_rom(args.rom_path)
    info = GameInfo(rom.game, rom.region, True)

    c_ptrs = find_code_ptrs(rom)
    sh_ptrs = find_sound_header_ptrs(rom, info)
    t_ptrs = find_track_ptrs(rom)
    d_ptrs = find_data_ptrs(rom, info)
    all_ptrs = sorted(c_ptrs + sh_ptrs + t_ptrs + d_ptrs)
    assert len(set(all_ptrs)) == len(all_ptrs)
    for loc in all_ptrs:
        print(f"{loc:05X}")
