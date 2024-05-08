import argparse
from enum import Enum
from typing import Dict, List, Tuple

import argparse_utils as apu
from game_info import GameInfo
from info_entry import InfoEntry, CodeEntry, DataEntry
from rom import Rom, SIZE_32MB, ROM_OFFSET, ROM_END
from thumb import ThumbForm, ThumbInstruct


class RefType(Enum):
    BL = 1
    POOL = 2
    DATA = 3


class Ref:
    def __init__(self, addr: int, label: str, offset: int):
        assert (label is None) == (offset is None)
        self.addr = addr
        self.label = label
        self.offset = offset


class BlRef(Ref):

    def __init__(self, addr: int, label: str = None, offset: int = None):
        super().__init__(addr, label, offset)

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            "" if self.label is None else self.label,
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)


class PoolRef(Ref):

    def __init__(self,
        addr: int,
        ldrs: List[int],
        label: str = None,
        offset: int = None
    ):
        super().__init__(addr, label, offset)
        self.ldrs = ldrs

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            ",".join(f"{a:X}" for a in self.ldrs),
            "" if self.label is None else self.label,
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)


class DataRef(Ref):

    def __init__(self,
        addr: int,
        label: str = None,
        index: int = None,
        offset: int = None
    ):
        assert (label is None) == (index is None)
        super().__init__(addr, label, offset)
        self.index = index

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            "" if self.label is None else self.label,
            "" if self.index is None else f"{self.index:X}",
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)


class References(object):

    def __init__(self, rom: Rom, include_unk = False):
        self.rom = rom
        from_json = not include_unk
        self.info = GameInfo(rom.game, rom.region, from_json, include_unk)

    def find(self, addr: int) -> Tuple[List[BlRef], List[PoolRef], List[DataRef]]:
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

        bl_refs = []
        pool_refs = {}
        data_refs = []

        # check bl and ldr in code
        self.entries = self.info.code
        addr_val = addr
        if in_rom:
            addr_val += ROM_OFFSET
            if in_code:
                addr_val += 1
        for i in range(code_start, code_end, 2):
            inst = ThumbInstruct(rom, i)
            if inst.format == ThumbForm.LdPC:
                pool_addr = inst.pc_rel_addr()
                val = rom.read_32(pool_addr)
                if addr_val == val:
                    ref = pool_refs.get(pool_addr)
                    if ref is None:
                        ref = self.get_ref(pool_addr, RefType.POOL)
                        pool_refs[pool_addr] = ref
                    ref.ldrs.append(i)
            elif in_code and inst.format == ThumbForm.Link:
                if addr == inst.branch_addr():
                    ref = self.get_ref(i, RefType.BL)
                    bl_refs.append(ref)

        # check data
        self.entries = self.info.data
        for i in range(code_end, data_end, 4):
            val = rom.read_32(i)
            if addr_val == val:
                ref = self.get_ref(i, RefType.DATA)
                data_refs.append(ref)
        
        return bl_refs, list(pool_refs.values()), data_refs

    def find_all(self) -> List[Tuple[str, int, List[Ref]]]:
        # TODO: pass refs instead of putting it on self?
        self.refs: Dict[int, List[Ref]] = {}
        rom = self.rom
        code_start = rom.code_start()
        code_end = rom.code_end()
        data_end = rom.data_end()

        # check every ref in code
        self.entries = self.info.code
        for i in range(code_start, code_end, 2):
            # check for bl
            inst = ThumbInstruct(rom, i)
            if inst.format == ThumbForm.Link:
                bl_addr = inst.branch_addr()
                if bl_addr >= code_start and bl_addr < code_end:
                    self.add_ref(bl_addr, i, RefType.BL)
            # check for pool
            elif i % 4 == 0:
                self.check_addr(i, RefType.POOL)

        # check every ref in data
        self.entries = self.info.data
        self.entries.append(DataEntry(None, None, "u8", 1, data_end))
        for i in range(code_end, data_end, 4):
            self.check_addr(i, RefType.DATA)
        
        return sorted(self.refs.items())

    def check_addr(self, addr: int, kind: RefType) -> None:
        """Checks if an address contains a valid reference."""
        val = self.rom.read_32(addr)
        if val >= self.rom.code_start(True) and val < self.rom.data_end(True):
            val -= ROM_OFFSET
            if val < self.rom.code_end() and val % 4 == 1:
                # subtract one for thumb code pointers
                val -= 1
            self.add_ref(val, addr, kind)

    def add_ref(self, val: int, addr: int, kind: RefType) -> None:
        """Creates and adds the reference at the given address."""
        if val not in self.refs:
            self.refs[val] = []
        ref = self.get_ref(addr, kind)
        self.refs[val].append(ref)

    def get_prev_entry(self, addr: int) -> InfoEntry:
        left = 0
        right = len(self.entries) - 1
        result = None
        while left <= right:
            mid = (left + right) // 2
            if self.entries[mid].addr <= addr:
                result = self.entries[mid]
                left = mid + 1
            else:
                right = mid - 1
        return result

    def get_ref(self, addr: int, kind: RefType) -> Ref:
        # get closest entry before address
        entry = self.get_prev_entry(addr)
        # create reference based on type
        if kind == RefType.BL:
            return self.get_bl_ref(addr, entry)
        elif kind == RefType.POOL:
            return self.get_pool_ref(addr, entry)
        elif kind == RefType.DATA:
            return self.get_data_ref(addr, entry)
        else:
            raise NotImplementedError()

    def get_code_len(self, entry: CodeEntry) -> int:
        if isinstance(entry.size, int):
            return entry.size
        else:
            return entry.size[self.rom.region]
    
    def get_offset_within_entry(self, addr, entry_addr, entry_len) -> int:
        assert entry_addr <= addr
        offset = addr - entry_addr
        if offset < entry_len:
            return offset
        return -1

    def get_bl_ref(self, addr: int, entry: CodeEntry) -> BlRef:
        if entry is not None:
            length = self.get_code_len(entry)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                return BlRef(addr, entry.label, offset)
        return BlRef(addr)
    
    def get_pool_ref(self, addr: int, entry: CodeEntry) -> PoolRef:
        if entry is not None:
            length = self.get_code_len(entry)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                return PoolRef(addr, [], entry.label, offset)
        return PoolRef(addr, [])
    
    def get_data_ref(self, addr: int, entry: DataEntry) -> DataRef:
        if entry is not None:
            length = entry.get_size(self.info.structs)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                count = entry.get_count()
                idx = 0
                if count > 1:
                    size = length // count
                    idx = offset // size
                    offset %= size
                return DataRef(addr, entry.label, idx, offset)
        return DataRef(addr)
    

def output_section(refs: List[Ref], title: str, fields: List[str]) -> List[str]:
    lines = []
    num_refs = len(refs)
    if num_refs > 0:
        lines.append(f"{title} ({len(refs)}):")
        lines.append("\t".join(fields))
        for ref in refs:
            lines.append(str(ref))
        lines.append("")
    return lines


def print_refs(bls: List[BlRef], pools: List[PoolRef], datas: List[DataRef]) -> None:
    lines = []
    lines += output_section(bls, "Calls", ["addr", "label", "off"])
    lines += output_section(pools, "Pools", ["addr", "ldrs", "label", "off"])
    lines += output_section(datas, "Data", ["addr", "label", "idx", "off"])
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_arg(parser, apu.ArgType.ROM_PATH)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--addr", type=str)
    group.add_argument("-l", "--label", type=str)
    group.add_argument("--all", action="store_true")
    parser.add_argument("-u", "--unk", action="store_true")

    args = parser.parse_args()
    rom = apu.get_rom(args.rom_path)
    refs = References(rom, args.unk)

    if args.all:
        results = refs.find_all()
        for name, addr, refs in results:
            print(f"{name}\t{addr:06X}\t{len(refs)}")
    else:
        # get address
        addr = None
        if args.addr:
            try:
                addr = int(args.addr, 16)
            except:
                print(f"Invalid hex address {args.addr}")
                quit()
        elif args.label:
            entry = refs.info.get_entry(args.label)
            if entry is None:
                print("Label not found")
                quit()
            addr = entry.addr
        # find references and print
        bls, ldrs, dats = refs.find(addr)
        print_refs(bls, ldrs, dats)
