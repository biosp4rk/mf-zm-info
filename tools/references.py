# TODO:
# - Add argparse flags for including ram and output format
# - Handle pointers to the middle of data

import argparse
from enum import Enum, auto
from pathlib import Path
from typing import Any

import yaml

import argparse_utils as apu
from function import all_functions
from info.asset_type import TypeSpecKind, AssetType, SpecifierType, PointerType, ArrayType
from info.game_info import GameInfo
from info.info_entry import CodeEntry, DataEntry
from rom import Rom, ROM_END_MAX, ROM_OFFSET
from thumb import ThumbInstruct, ThumbForm


EWRAM_START = 0x200_0000
EWRAM_END = 0x204_0000
IWRAM_START = 0x300_0000
IWRAM_END = 0x300_8000

class RefType(Enum):
    BL = auto()
    POOL = auto()
    DATA = auto()


class Ref:
    key: str = None

    def __init__(self, addr: int, name: str, offset: int):
        assert (name is None) == (offset is None)
        self.addr = addr
        self.name = name
        self.offset = offset

    def to_obj(self, include_addr: bool) -> Any:
        raise NotImplementedError()


class BlRef(Ref):
    key = "call"

    def __init__(self, addr: int, name: str = None, offset: int = None):
        super().__init__(addr, name, offset)

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            "" if self.name is None else self.name,
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)
    
    def __repr__(self) -> str:
        items = ["bl", f"{self.addr:X}"]
        if self.name:
            items.append(self.name)
            items.append(f"{self.offset:X}")
        return ",".join(items)

    def to_obj(self, include_addr: bool) -> Any:
        obj = []
        if include_addr:
            obj.append(("addr", self.addr))
        if self.name:
            obj.append(("name", self.name))
            obj.append(("offset", self.offset))
        return dict(obj)


class PoolRef(Ref):
    key = "pool"

    def __init__(self,
        addr: int,
        ldrs: list[int],
        name: str = None,
        offset: int = None
    ):
        super().__init__(addr, name, offset)
        self.ldrs = ldrs

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            ",".join(f"{a:X}" for a in self.ldrs),
            "" if self.name is None else self.name,
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)

    def __repr__(self) -> str:
        items = ["pool", f"{self.addr:X}"]
        if self.name:
            items.append(self.name)
            items.append(f"{self.offset:X}")
        return ",".join(items)
    
    def to_obj(self, include_addr: bool) -> Any:
        obj = []
        if include_addr:
            obj.append(("addr", self.addr))
        if self.name:
            obj.append(("name", self.name))
            obj.append(("offset", self.offset))
        return dict(obj)


class DataRef(Ref):
    key = "data"

    def __init__(self,
        addr: int,
        name: str = None,
        index: int = None,
        offset: int = None
    ):
        assert (name is None) == (index is None)
        super().__init__(addr, name, offset)
        self.index = index

    def __str__(self) -> str:
        items = [
            f"{self.addr:X}",
            "" if self.name is None else self.name,
            "" if self.index is None else f"{self.index:X}",
            "" if self.offset is None else f"{self.offset:X}"
        ]
        return "\t".join(items)

    def __repr__(self) -> str:
        items = ["data", f"{self.addr:X}"]
        if self.name:
            items.append(self.name)
            items.append(f"{self.index:X}")
            items.append(f"{self.offset:X}")
        return ",".join(items)

    def to_obj(self, include_addr: bool) -> Any:
        obj = []
        if include_addr:
            obj.append(("addr", self.addr))
        if self.name:
            obj.append(("name", self.name))
            obj.append(("index", self.index))
            obj.append(("offset", self.offset))
        return dict(obj)


class References(object):
    def __init__(self, rom: Rom, include_ram: bool = True):
        self.rom = rom
        self.include_ram = include_ram
        self.info = GameInfo(rom.game, rom.region)

    def find_all(self) -> dict[int, list[Ref]]:
        found_refs: dict[int, list[Ref]] = {}
        info = self.info
        rom = self.rom

        # Check every ref in code
        code_addrs = {c.addr: c for c in info.code}
        for func in all_functions(rom):
            pool_refs: dict[int, PoolRef] = {}
            entry = code_addrs.get(func.start_addr)
            # Check for bl and ldr
            for addr, inst in func.instructs.items():
                if inst.format == ThumbForm.Link:
                    bl_addr = inst.branch_addr()
                    if bl_addr >= func.start_addr and bl_addr < func.end_addr:
                        continue
                    self.add_ref(found_refs, bl_addr, addr, RefType.BL, entry)
                elif inst.format == ThumbForm.LdPC:
                    pool_addr = inst.pc_rel_addr()
                    ref = pool_refs.get(pool_addr)
                    if ref is None:
                        # Skip if it's a jump table
                        val = rom.read_32(pool_addr) - ROM_OFFSET
                        if val >= func.start_addr and val < func.end_addr:
                            continue
                        # Try creating/adding new ref
                        ref = self.check_addr(pool_addr, RefType.POOL, found_refs, entry)
                        if ref is None:
                            continue
                        assert isinstance(ref, PoolRef)
                        pool_refs[pool_addr] = ref
                    ref.ldrs.append(addr)

        # Check every ref in data
        for entry in info.data:
            if not entry.has_ptr(info.structs, info.unions, info.types):
                continue
            addr = entry.addr
            for _ in range(entry.get_count()):
                self.find_data_ref(found_refs, addr, entry.type, entry)
                addr += entry.type.get_size(info.sizes, info.types)

        return found_refs

    def find(self, addr: int) -> tuple[list[BlRef], list[PoolRef], list[DataRef]]:
        if addr >= ROM_OFFSET and addr < ROM_END_MAX:
            addr -= ROM_OFFSET
        code_end = self.rom.code_end()
        is_code = addr < code_end

        all_refs = self.find_all()
        bl_refs: list[BlRef] = []
        pool_refs: list[PoolRef] = []
        data_refs: list[DataRef] = []
        for refs in all_refs.values():
            for ref in refs:
                if isinstance(ref, BlRef):
                    inst = ThumbInstruct(self.rom, ref.addr)
                    if inst.format == ThumbForm.Link and inst.branch_addr == addr:
                        bl_refs.append(ref)
                else:
                    val = self.rom.read_32(ref.addr)
                    if val >= ROM_OFFSET:
                        val -= ROM_OFFSET
                    if is_code:
                        if val >= code_end:
                            continue
                        if val % 4 == 1:
                            val -= 1
                    if val != addr:
                        continue
                    if isinstance(ref, PoolRef):
                        pool_refs.append(ref)
                    elif isinstance(ref, DataRef):
                        data_refs.append(ref)
        return bl_refs, pool_refs, data_refs

    def find_data_ref(self,
        found_refs: dict[int, list[Ref]],
        addr: int,
        type: AssetType,
        entry: DataEntry
    ) -> None:
        info = self.info
        if isinstance(type, PointerType):
            self.check_addr(addr, RefType.DATA, found_refs, entry)
        elif isinstance(type, ArrayType):
            inner = type.inner_type
            size = inner.get_size(info.sizes, info.types)
            for i in range(type.size):
                self.find_data_ref(found_refs, addr + i * size, inner, entry)
        elif isinstance(type, SpecifierType):
            if type.kind == TypeSpecKind.STRUCT:
                struct = info.structs[type.spec_name()]
                for sv in struct.vars:
                    type = sv.type
                    # Align
                    alignment = type.get_alignment(info.types)
                    if addr % alignment != 0:
                        addr += alignment - (addr % alignment)
                    self.find_data_ref(found_refs, addr, type, entry)
                    addr += type.get_size(info.sizes, info.types)
            elif type.kind == TypeSpecKind.UNION:
                union = info.unions[type.spec_name()]
                for uv in union.vars:
                    self.find_data_ref(found_refs, addr, uv.type, entry)
            elif type.kind == TypeSpecKind.TYPEDEF:
                type = info.types[type.spec_name()]
                self.find_data_ref(found_refs, addr, type, entry)
            elif type.kind == TypeSpecKind.BUILT_IN:
                return
            else:
                raise ValueError(f"Unsupported TypeSpecKind {type.kind}")
        else:
            raise ValueError(f"Unsupported type: {type}")

    def check_addr(self,
        addr: int,
        kind: RefType,
        found_refs: dict[int, list[Ref]],
        entry: CodeEntry | DataEntry
    ) -> Ref:
        """Checks if an address contains a valid reference."""
        val = self.rom.read_32(addr)
        if val >= self.rom.code_start(True) and val < self.rom.data_end(True):
            val -= ROM_OFFSET
            if val < self.rom.code_end() and val % 4 == 1:
                # Subtract one for thumb code pointers
                val -= 1
        elif (
            self.include_ram and
            ((val >= EWRAM_START and val < EWRAM_END) or
            (val >= IWRAM_START and val < IWRAM_END))
        ):
            pass
        else:
            return None
        return self.add_ref(found_refs, val, addr, kind, entry)

    def add_ref(self,
        found_refs: dict[int, list[Ref]],
        val: int,
        addr: int,
        kind: RefType,
        entry: CodeEntry | DataEntry
    ) -> Ref:
        """Creates and adds the reference at the given address."""
        ref = self.get_ref(addr, kind, entry)
        if val not in found_refs:
            found_refs[val] = []
        found_refs[val].append(ref)
        return ref

    def get_ref(self, addr: int, kind: RefType, entry: CodeEntry | DataEntry) -> Ref:
        # Create reference based on type
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
        assert offset < entry_len
        return offset

    def get_bl_ref(self, addr: int, entry: CodeEntry) -> BlRef:
        if entry is not None:
            length = self.get_code_len(entry)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                return BlRef(addr, entry.name, offset)
        return BlRef(addr)
    
    def get_pool_ref(self, addr: int, entry: CodeEntry) -> PoolRef:
        if entry is not None:
            length = self.get_code_len(entry)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                return PoolRef(addr, [], entry.name, offset)
        return PoolRef(addr, [])
    
    def get_data_ref(self, addr: int, entry: DataEntry) -> DataRef:
        if entry is not None and not isinstance(entry, CodeEntry):
            length = entry.get_size(self.info.sizes, self.info.types)
            offset = self.get_offset_within_entry(addr, entry.addr, length)
            if offset != -1:
                count = entry.get_count()
                idx = 0
                if count > 1:
                    size = length // count
                    idx = offset // size
                    offset %= size
                return DataRef(addr, entry.name, idx, offset)
        return DataRef(addr)
    

def output_section(refs: list[Ref], title: str, fields: list[str]) -> list[str]:
    lines = []
    num_refs = len(refs)
    if num_refs > 0:
        lines.append(f"{title} ({len(refs)}):")
        lines.append("\t".join(fields))
        for ref in refs:
            lines.append(str(ref))
        lines.append("")
    return lines


def print_refs(bls: list[BlRef], pools: list[PoolRef], datas: list[DataRef]) -> None:
    lines = []
    lines += output_section(bls, "Calls", ["addr", "name", "off"])
    lines += output_section(pools, "Pools", ["addr", "ldrs", "name", "off"])
    lines += output_section(datas, "Data", ["addr", "name", "idx", "off"])
    print("\n".join(lines))


def output_all_refs(out_dir: str, all_refs: dict[int, list[Ref]], info: GameInfo) -> None:
    entry_names = {
        "ram": {e.addr: e.name for e in info.ram},
        "code": {e.addr: e.name for e in info.code},
        "data": {e.addr: e.name for e in info.data}
    }
    results = {mt: {} for mt in entry_names}
    for addr, refs in sorted(all_refs.items()):
        for map_type, names in entry_names.items():
            name = names.get(addr)
            if name is not None:
                entry: dict[str, list] = {}
                for ref in refs:
                    if ref.key not in entry:
                        entry[ref.key] = []
                    entry[ref.key].append(ref.to_obj(False))
                results[map_type][name] = entry
                break
    out_path = Path(out_dir)
    out_path.mkdir(exist_ok=True)
    for map_type, entries in results.items():
        with open(out_path.joinpath(f"{map_type}.yml"), "w") as f:
            yaml.safe_dump(entries, f, sort_keys=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    apu.add_rom(parser)
    subparsers = parser.add_subparsers(dest="command")

    single_parser = subparsers.add_parser("single")
    group = single_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--addr", type=apu.hex_arg)
    group.add_argument("-n", "--name", type=str)

    all_parser = subparsers.add_parser("all")
    all_parser.add_argument("out_dir", type=str)

    args = parser.parse_args()
    rom = args.rom_path
    refs = References(rom)

    if args.command == "all":
        all_refs = refs.find_all()
        output_all_refs(args.out_dir, all_refs, refs.info)
    else:
        # Get address
        addr = None
        if args.addr is not None:
            addr = args.addr
        elif args.name:
            entry = refs.info.get_entry(args.name)
            if entry is None:
                print("Label not found")
                quit()
            addr = entry.addr
        # Find references and print
        bls, ldrs, dats = refs.find(addr)
        print_refs(bls, ldrs, dats)
