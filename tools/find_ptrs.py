import argparse
from enum import Enum
from typing import List, Tuple, Union

import argparse_utils as apu
from constants import *
from function import all_functions
from game_info import GameInfo
from info_entry import PrimType, DataEntry, StructEntry, StructVarEntry, CodeEntry
from rom import Rom, ROM_OFFSET


class Validity(Enum):
    UNKNOWN = 0
    INVALID = 1
    VALID = 2

VALID_STR = {
    Validity.UNKNOWN: "unk",
    Validity.INVALID: "no",
    Validity.VALID: "yes"
}


class Status(Enum):
    UNKNOWN = 0
    # The primitive at the pointer's location is not 4-byte aligned (invalid)
    LOC_NOT_ALIGNED = 1
    # The primitive at the pointer's location is not a pointer (invalid)
    LOC_NOT_PTR = 2
    # The primitive at the pointer's location is a pointer (valid)
    LOC_IS_PTR = 3
    # The pointer points to the middle of a function (invalid)
    PTR_CODE_MIDDLE = 4
    # The pointer points to the start of a function (likely valid)
    PTR_CODE = 5
    # The pointer points to the middle of a data entry (likely invalid)
    PTR_DATA_MIDDLE = 6
    # The pointer points to the start of a piece of data (likely valid)
    PTR_DATA = 7

STATUS_STR = {
    Status.UNKNOWN: "unk",
    Status.LOC_NOT_ALIGNED: "loc not aligned",
    Status.LOC_NOT_PTR: "loc not ptr",
    Status.LOC_IS_PTR: "loc is ptr",
    Status.PTR_CODE_MIDDLE: "ptr middle code",
    Status.PTR_CODE: "ptr code",
    Status.PTR_DATA_MIDDLE: "ptr middle data",
    Status.PTR_DATA: "ptr data",
}


class PtrLoc:
    def __init__(self,
        loc_addr: int,
        ptr_val: int,
        validity = Validity.UNKNOWN,
        status = Status.UNKNOWN,
        entry: Union[DataEntry, CodeEntry] = None
    ):
        self.loc_addr = loc_addr
        self.ptr_val = ptr_val
        self.validity = validity
        self.status = status
        self.entry = entry

    def print(self, diff: int) -> None:
        entry = f"{self.entry.addr:X} {self.entry.label}" if self.entry else ""
        print("\t".join([
            f"{self.loc_addr:X}",
            f"{self.ptr_val:X}",
            f"{diff:X}",
            VALID_STR[self.validity],
            STATUS_STR[self.status],
            entry
        ]))


def find_code_ptrs(rom: Rom) -> List[int]:
    """Finds all pointers in code data pools. These are all assumed to be valid."""
    v_code_start = rom.code_start(True)
    v_data_end = rom.data_end(True)
    ptr_locs: List[int] = []
    funcs = all_functions(rom)
    for func in funcs:
        ptr_locs += func.get_jump_tables()
        for loc in func.data_pool:
            val = rom.read_32(loc)
            # check if value falls within rom
            if val >= v_code_start and val < v_data_end:
                ptr_locs.append(loc)
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
        num_tracks = rom.read_8(addr)
        if num_tracks == 0:
            continue
        #ptr_locs.append(addr + 4)
        for j in range(num_tracks):
            ptr_locs.append(addr + 8 + (j * 4))
    ptr_locs.sort()
    return ptr_locs


def get_track_start_end(rom: Rom) -> Tuple[int, int]:
    """Returns the start and end address of all track data."""
    addrs = None
    if rom.game == GAME_MF:
        if rom.region == REGION_U:
            addrs = (0x25895C, 0x289960)
    elif rom.game == GAME_ZM:
        if rom.region == REGION_U:
            addrs = (0x20B090, 0x2320B0)
    if addrs is None:
        raise NotImplementedError()
    return addrs


def find_track_ptrs(rom: Rom):
    """Finds all pointers within track data (these don't need to be 4-byte aligned)."""
    start, end = get_track_start_end(rom)
    v_start = start + ROM_OFFSET
    v_end = end + ROM_OFFSET
    ptr_locs: List[int] = []
    for addr in range(start, end):
        val = rom.read_8(addr)
        if val != 0xB2 and val != 0xB3:
            continue
        addr += 1
        val = rom.read_32(addr)
        if val < v_start or val >= v_end:
            continue
        val -= ROM_OFFSET
        if val >= addr:
            continue
        ptr_locs.append(addr)
    return ptr_locs


def find_data_ptrs(rom: Rom, info: GameInfo) -> List[int]:
    code_dict = {c.addr: c for c in info.code}
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
        val = rom.read_32(addr)
        if val < v_code_start or val >= v_data_end:
            continue
        val -= ROM_OFFSET
        # check if this address falls within a known asset
        validity = Validity.UNKNOWN
        status = Status.UNKNOWN
        main_entry = None
        idx, entry, _, _ = find_prim_at_offset(data_list, idx, addr, info)
        if entry:
            main_entry = data_list[idx]
            if main_entry.addr % 4 != 0:
                validity = Validity.INVALID
                status = Status.LOC_NOT_ALIGNED
            elif not entry.is_ptr():
                validity = Validity.INVALID
                status = Status.LOC_NOT_PTR
            else:
                validity = Validity.VALID
                status = Status.LOC_IS_PTR
        
        # check if the value points to known asset
        else:
            if val < code_end:
                # check if value points to code
                # subtract one for thumb code pointers
                val -= 1
                if val not in code_dict:
                    status = Status.PTR_CODE_MIDDLE
                else:
                    main_entry = code_dict[val]
                    status = Status.PTR_CODE
            else:
                # check if value points to known data
                j, entry, prim_idx, prim_off = find_prim_at_offset(data_list, 0, val, info)
                if entry:
                    main_entry = data_list[j]
                    if prim_idx != 0 or prim_off != 0:
                        status = Status.PTR_DATA_MIDDLE
                    else:
                        status = Status.PTR_DATA
        # print
        ptr_loc = PtrLoc(addr, val, validity, status, main_entry)
        diff = addr - prev_addr
        ptr_loc.print(diff)
        if validity != Validity.INVALID:
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
    Returns (entry_index, entry, prim_num, prim_offset).
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
        if not is_ptr and entry.primitive == PrimType.STRUCT:
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
    info = GameInfo(rom.game, rom.region, False, True)

    c_ptrs = find_code_ptrs(rom)
    sh_ptrs = find_sound_header_ptrs(rom, info)
    t_ptrs = find_track_ptrs(rom)
    d_ptrs = find_data_ptrs(rom, info)
    all_ptrs = sorted(c_ptrs + sh_ptrs + t_ptrs + d_ptrs)
    assert len(set(all_ptrs)) == len(all_ptrs)
    for loc in all_ptrs:
        print(f"{loc:05X}")
