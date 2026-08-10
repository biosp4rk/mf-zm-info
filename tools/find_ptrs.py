import argparse

import argparse_utils as apu
from constants import *
from function import Function
from info.asset_type import AssetType, ArrayType, PointerType, SpecifierType, TypeSpecKind
from info.game_info import GameInfo, InfoSource
from rom import Rom, ROM_OFFSET, SIZE_8MB


class PtrLoc:
    def __init__(self, name: str, idx: int):
        self.name = name
        self.idx = idx


class PtrFinder:
    def __init__(self, rom: Rom, info: GameInfo):
        self.rom = rom
        self.info = info

    def find_ptrs(self) -> set[int]:
        print("Finding code pointers...")
        ptr_locs = self._find_code_ptrs()
        ptr_locs = set()
        print("Finding data pointers...")
        ptr_locs.update(self._find_data_ptrs())
        return ptr_locs

    def _find_code_ptrs(self) -> set[int]:
        rom = self.rom
        v_data_start = rom.data_start(True)
        v_data_end = rom.data_end(True)
        ptr_locs: set[int] = set()
        for entry in self.info.code:
            func = Function(rom, entry.addr)
            for loc in func.data_pool:
                val = rom.read_32(loc)
                # Check if value falls within rom
                if val >= v_data_start and val < v_data_end:
                    ptr_locs.add(loc)
        return ptr_locs

    def _find_data_ptrs(self) -> set[int]:
        info = self.info
        ptr_locs: set[int] = set()
        for entry in info.data:
            if not entry.has_ptr(info.structs, info.unions, info.types):
                continue
            addr = entry.addr
            for _ in range(entry.get_count()):
                self._find_data_ptr(ptr_locs, addr, entry.type)
                addr += entry.type.get_size(info.sizes, info.types)
        return ptr_locs

    def _find_data_ptr(self, ptr_locs: set[int], addr: int, type: AssetType) -> None:
        info = self.info
        if isinstance(type, PointerType):
            val = rom.read_32(addr)
            if val >= rom.data_start(True) and val < ROM_OFFSET + SIZE_8MB:
                ptr_locs.add(addr)
        elif isinstance(type, ArrayType):
            inner = type.inner_type
            size = inner.get_size(info.sizes, info.types)
            for i in range(size):
                self._find_data_ptr(ptr_locs, addr + i * size, inner)
        elif isinstance(type, SpecifierType):
            if type.kind == TypeSpecKind.STRUCT:
                struct = info.structs[type.spec_name()]
                for sv in struct.vars:
                    type = sv.type
                    # Align
                    alignment = type.get_alignment(info.types)
                    if addr % alignment != 0:
                        addr += alignment - (addr % alignment)
                    self._find_data_ptr(ptr_locs, addr, type)
                    addr += type.get_size(info.sizes, info.types)
            elif type.kind == TypeSpecKind.UNION:
                union = info.unions[type.spec_name()]
                for uv in union.vars:
                    self._find_data_ptr(ptr_locs, addr, uv.type)
            elif type.kind == TypeSpecKind.TYPEDEF:
                type = info.types[type.spec_name()]
                self._find_data_ptr(ptr_locs, addr, type)
            else:
                raise ValueError(f"Unsupported TypeSpecKind {type.kind}")
        else:
            raise ValueError(f"Unsupported type: {type}")
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_rom(parser)

    args = parser.parse_args()
    rom = args.rom_path
    print("Loading game info...")
    info = GameInfo(rom.game, rom.region, InfoSource.JSON)

    ptr_finder = PtrFinder(rom, info)
    ptr_locs = ptr_finder.find_ptrs()

    for loc in sorted(ptr_locs):
        print(f"{loc:X}")
    print(len(ptr_locs))
