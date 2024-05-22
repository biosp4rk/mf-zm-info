from abc import ABC, abstractmethod
from enum import Enum
import re
from typing import Any, Dict, List, Union

from constants import *


# type for numbers that can vary by region (addr, size)
RegionInt = Union[int, Dict[str, int]]
StructDict = Dict[str, "StructEntry"]


class PrimType(Enum):
    U8 = 1
    S8 = 2
    U16 = 3
    S16 = 4
    U32 = 5
    S32 = 6
    STRUCT = 7
    VOID = 8

PRIM_TO_STR = {
    PrimType.U8: "u8",
    PrimType.S8: "s8",
    PrimType.U16: "u16",
    PrimType.S16: "s16",
    PrimType.U32: "u32",
    PrimType.S32: "s32",
    PrimType.VOID: "void"
}

STR_TO_PRIM = {s: p for p, s in PRIM_TO_STR.items()}


class Category(Enum):
    BOOL = 1
    FLAGS = 2
    ASCII = 3
    SJIS = 4
    TEXT = 5
    GFX = 6
    TILEMAP = 7
    PALETTE = 8
    OAM_FRAME = 9
    BG_BLOCKS = 10
    BG_MAP = 11
    PCM = 12
    THUMB = 13
    ARM = 14

CAT_TO_STR = {
    Category.BOOL: "bool",
    Category.FLAGS: "flags",
    Category.ASCII: "ascii",
    Category.SJIS: "sjis",
    Category.TEXT: "text",
    Category.GFX: "gfx",
    Category.TILEMAP: "tilemap",
    Category.PALETTE: "palette",
    Category.OAM_FRAME: "oam_frame",
    Category.BG_BLOCKS: "bg_blocks",
    Category.BG_MAP: "bg_map",
    Category.PCM: "pcm",
    Category.THUMB: "thumb",
    Category.ARM: "arm"
}

STR_TO_CAT = {s: c for c, s in CAT_TO_STR.items()}


class Compression(Enum):
    RLE = 1
    LZ = 2

COMP_TO_STR = {
    Compression.RLE: "rle",
    Compression.LZ: "lz"
}

STR_TO_COMP = {s: c for c, s in COMP_TO_STR.items()}


class CodeMode(Enum):
    Thumb = 1
    Arm = 2

MODE_TO_STR = {
    CodeMode.Thumb: "thumb",
    CodeMode.Arm: "arm"
}

STR_TO_MODE = {s: m for m, s in MODE_TO_STR.items()}


class InfoEntry(ABC):

    def __init__(self, desc: str, label: str, notes: str = None):
        self.desc = desc
        self.label = label
        self.notes = notes

    def __lt__(self, other: "InfoEntry") -> bool:
        return self.label < other.label

    def to_region(self, region: str) -> bool:
        return True

    @staticmethod
    @abstractmethod
    def from_obj(obj: Any) -> "InfoEntry":
        pass

    @staticmethod
    @abstractmethod
    def to_obj(entry: "InfoEntry") -> Any:
        pass

    @staticmethod
    def less_than(ri1: RegionInt, ri2: RegionInt) -> bool:
        # get region dictionaries
        addr1 = ri1
        addr2 = ri2
        if isinstance(ri1, int):
            addr1 = {r: ri1 for r in REGIONS}
        if isinstance(ri2, int):
            addr2 = {r: ri2 for r in REGIONS}
        # compare by first region containing both
        for r in REGIONS:
            if r in addr1 and r in addr2:
                return addr1[r] < addr2[r]
        # entries are unique to each region,
        # so they're not directly comparable;
        # just compare averages instead
        avg1 = sum(addr1.values()) / len(addr1)
        avg2 = sum(addr2.values()) / len(addr2)
        return avg1 < avg2


class VarEntry(InfoEntry):

    def __init__(self,
        desc: str,
        label: str,
        type: str,
        # arr_count of None implies no array
        # arr_count of 1 implies array [1]
        arr_count: RegionInt,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None,
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.parse_type(type)
        self.arr_count = arr_count
        self.cat = cat
        self.comp = comp
        self.enum = enum

    def __str__(self) -> str:
        return self.label

    def parse_type(self, type: str):
        parts = type.split()
        # primitive
        prim = parts[0]
        pt = STR_TO_PRIM.get(prim)
        if pt is not None:
            self.primitive = pt
            self.struct_name = None
        else:
            self.primitive = PrimType.STRUCT
            self.struct_name = prim
        # declaration
        if len(parts) == 2:
            self.declaration = parts[1]
        else:
            self.declaration = None

    def inner_decl(self) -> str:
        """
        Returns inner-most part of declaration.
        """
        decl = self.declaration
        i = decl.rfind("(")
        if i != -1:
            i += 1
            j = decl.find(")", i)
            decl = decl[i:j]
        return decl

    def spec(self) -> str:
        """
        Returns the base type name (without pointers and arrays).
        """
        if self.primitive == PrimType.STRUCT:
            return self.struct_name
        return PRIM_TO_STR[self.primitive]

    def type_str(self) -> str:
        if self.declaration is None:
            return self.spec()
        return f"{self.spec()} {self.declaration}"

    def is_ptr(self) -> bool:
        if not self.declaration:
            return False
        return self.inner_decl().startswith("*")

    def has_ptr(self, structs: StructDict) -> bool:
        if self.is_ptr():
            return True
        if self.primitive == PrimType.STRUCT:
            se = structs[self.struct_name]
            if any(v.has_ptr(structs) for v in se.vars):
                return True
        return False

    def get_count(self) -> int:
        """Gets the count of the outermost array"""
        if self.arr_count is None:
            return 1
        if isinstance(self.arr_count, dict):
            for r in REGIONS:
                if r in self.arr_count:
                    return self.arr_count[r]
        else:
            return self.arr_count

    def get_total_count(self) -> int:
        """Gets the total count, including nested arrays"""
        count = self.get_count()
        if self.declaration is not None:
            decl = self.inner_decl()
            # check for array
            mc = re.findall(r"\w+", decl)
            for m in mc:
                count *= int(m, 16)
        return count

    def get_size(self, structs: StructDict) -> int:
        """Gets the total size of the entry"""
        size = 4 if self.is_ptr() else self.get_spec_size(structs)
        return size * self.get_total_count()

    def get_spec_size(self, structs: StructDict) -> int:
        """Gets the size of a single item of this type"""
        if self.primitive in {
            PrimType.VOID,
            PrimType.U8,
            PrimType.S8
        }:
            return 1
        elif (self.primitive == PrimType.U16 or
            self.primitive == PrimType.S16):
            return 2
        elif (self.primitive == PrimType.U32 or
            self.primitive == PrimType.S32):
            return 4
        elif self.primitive == PrimType.STRUCT:
            se = structs.get(self.struct_name)
            if se is not None:
                return se.size
            msg = f"Invalid struct name {self.struct_name}"
            raise ValueError(msg)

    def get_alignment(self, structs: StructDict) -> int:
        if self.is_ptr():
            return 4
        if self.primitive == PrimType.STRUCT:
            se = structs[self.struct_name]
            return max(v.get_alignment(structs) for v in se.vars)
        return self.get_spec_size(structs)

    @staticmethod
    def from_obj(obj: Any) -> "VarEntry":
        cat = None
        if K_CAT in obj:
            cat = STR_TO_CAT[obj[K_CAT]]
        comp = None
        if K_COMP in obj:
            comp = STR_TO_COMP[obj[K_COMP]]
        return VarEntry(
            obj[K_DESC],
            obj[K_LABEL],
            obj[K_TYPE],
            obj.get(K_COUNT),
            cat,
            comp,
            obj.get(K_ENUM),
            obj.get(K_NOTES)
        )

    @staticmethod
    def to_obj(entry: "VarEntry") -> Any:
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)


class DataEntry(VarEntry):

    def __init__(self,
        desc: str,
        label: str,
        type: str,
        arr_count: RegionInt,
        addr: RegionInt,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None,
        notes: str = None
    ):
        super().__init__(
            desc, label, type, arr_count, cat, comp, enum, notes
        )
        self.addr = addr

    def __str__(self) -> str:
        return f"{self.label}"

    def __lt__(self, other: "DataEntry") -> bool:
        return InfoEntry.less_than(self.addr, other.addr)

    def to_region(self, region: str) -> bool:
        # check addr
        if isinstance(self.addr, dict):
            if region not in self.addr:
                return False
            self.addr = self.addr[region]
        # check arr_count
        if isinstance(self.arr_count, dict):
            if region in self.arr_count:
                self.arr_count = self.arr_count[region]
        return True

    @staticmethod
    def from_obj(obj: Any) -> "DataEntry":
        try:
            cat = None
            if K_CAT in obj:
                cat = STR_TO_CAT[obj[K_CAT]]
            comp = None
            if K_COMP in obj:
                comp = STR_TO_COMP[obj[K_COMP]]
            return DataEntry(
                obj[K_DESC],
                obj[K_LABEL],
                obj[K_TYPE],
                obj.get(K_COUNT),
                obj[K_ADDR],
                cat,
                comp,
                obj.get(K_ENUM),
                obj.get(K_NOTES)
            )
        except:
            raise Exception(f"Error parsing data entry: {obj}")

    @staticmethod
    def to_obj(entry: "DataEntry") -> Any:
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        obj.append((K_ADDR, entry.addr))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)


class StructVarEntry(VarEntry):

    def __init__(self,
        desc: str,
        label: str,
        type: str,
        arr_count: RegionInt,
        offset: RegionInt,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None,
        notes: str = None
    ):
        super().__init__(
            desc, label, type, arr_count, cat, comp, enum, notes
        )
        self.offset = offset

    def __str__(self) -> str:
        return f"{self.offset:X} {self.label}"

    def __lt__(self, other: "StructVarEntry") -> bool:
        return InfoEntry.less_than(self.offset, other.offset)

    def to_region(self, region: str) -> bool:
        # check offset
        if isinstance(self.offset, dict):
            if region not in self.offset:
                return False
            self.offset = self.offset[region]
        # check arr_count
        if isinstance(self.arr_count, dict):
            if region in self.arr_count:
                self.arr_count = self.arr_count[region]
        return True

    @staticmethod
    def from_obj(obj: Any) -> "StructVarEntry":
        cat = None
        if K_CAT in obj:
            cat = STR_TO_CAT[obj[K_CAT]]
        comp = None
        if K_COMP in obj:
            comp = STR_TO_COMP[obj[K_COMP]]
        return StructVarEntry(
            obj[K_DESC],
            obj[K_LABEL],
            obj[K_TYPE],
            obj.get(K_COUNT),
            obj[K_OFFSET],
            cat,
            comp,
            obj.get(K_ENUM),
            obj.get(K_NOTES)
        )

    @staticmethod
    def to_obj(entry: "StructVarEntry") -> Any:
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        obj.append((K_OFFSET, entry.offset))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)


class StructEntry(InfoEntry):

    def __init__(self,
        desc: str,
        label: str,
        size: int,
        vars: List[StructVarEntry],
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.size = size
        self.vars = vars

    def __str__(self) -> str:
        return f"Size: {self.size:X}"

    def get_var(self, label: str) -> StructVarEntry:
        for var in self.vars:
            if var.label == label:
                return var
        return None

    @staticmethod
    def from_obj(obj: Any) -> "StructEntry":
        try:
            vars = [StructVarEntry.from_obj(e) for e in obj[K_VARS]]
            return StructEntry(
                obj[K_DESC],
                obj[K_LABEL],
                obj[K_SIZE],
                vars,
                obj.get(K_NOTES)
            )
        except:
            raise Exception(f"Error parsing struct entry: {obj}")

    @staticmethod
    def to_obj(entry: "StructEntry") -> Any:
        vars = [StructVarEntry.to_obj(e) for e in entry.vars]
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_SIZE, entry.size),
            (K_VARS, vars)
        ]
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)


class CodeEntry(InfoEntry):

    def __init__(self,
        desc: str,
        label: str,
        addr: RegionInt,
        size: RegionInt,
        mode: CodeMode,
        params: List[VarEntry],
        ret: VarEntry,
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.addr = addr
        self.size = size
        self.mode = mode
        self.params = params
        self.ret = ret

    def __str__(self) -> str:
        return f"{self.label}"

    def __lt__(self, other: "CodeEntry") -> bool:
        return InfoEntry.less_than(self.addr, other.addr)

    def to_region(self, region: str) -> bool:
        # check addr
        if isinstance(self.addr, dict):
            if region not in self.addr:
                return False
            self.addr = self.addr[region]
        # check size
        if isinstance(self.size, dict):
            if region in self.size:
                self.size = self.size[region]
        return True

    def is_thumb(self) -> bool:
        return self.mode == CodeMode.Thumb

    @staticmethod
    def from_obj(obj: Any) -> "CodeEntry":
        try:
            params = obj[K_PARAMS]
            # TODO: don't allow str for params
            if not isinstance(params, str):
                params = [VarEntry.from_obj(p) for p in params] if params else None
            ret = obj[K_RETURN]
            # TODO: don't allow str for return
            if not isinstance(ret, str):
                ret = VarEntry.from_obj(ret) if ret else None
            return CodeEntry(
                obj[K_DESC],
                obj[K_LABEL],
                obj[K_ADDR],
                obj[K_SIZE],
                STR_TO_MODE[obj[K_MODE]],
                params,
                ret,
                obj.get(K_NOTES)
            )
        except:
            raise Exception(f"Error parsing code entry: {obj}")

    @staticmethod
    def to_obj(entry: "CodeEntry") -> Any:
        mode = "arm" if entry.mode == CodeMode.Arm else "thumb"
        # TODO: don't allow str for params
        params = entry.params
        if not isinstance(entry.params, str):
            params = [VarEntry.to_obj(p) for p in entry.params] if entry.params else None
        # TODO: don't allow str for return
        ret = entry.ret
        if not isinstance(entry.ret, str):
            ret = VarEntry.to_obj(entry.ret) if entry.ret else None
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_ADDR, entry.addr),
            (K_SIZE, entry.size),
            (K_MODE, MODE_TO_STR[entry.mode]),
            (K_PARAMS, params),
            (K_RETURN, ret),
        ]
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)


class EnumValEntry(InfoEntry):

    def __init__(self,
        desc: str,
        label: str,
        val: int,
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.val = val

    def __str__(self) -> str:
        return f"{self.val:X} {self.label}"

    def __lt__(self, other: "EnumValEntry") -> bool:
        return self.val < other.val

    @staticmethod
    def from_obj(obj: Any) -> "EnumValEntry":
        return EnumValEntry(
            obj[K_DESC],
            obj[K_LABEL],
            obj[K_VAL],
            obj.get(K_NOTES)
        )

    @staticmethod
    def to_obj(entry: "EnumValEntry") -> Any:
        obj = [
            ("desc", entry.desc),
            ("label", entry.label),
            ("val", entry.val)
        ]
        if entry.notes:
            obj.append(("notes", entry.notes))
        return dict(obj)


class EnumEntry(InfoEntry):

    def __init__(self,
        desc: str,
        label: str,
        vals: List[EnumValEntry],
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.vals = vals

    def __str__(self) -> str:
        return f"# vals: {len(self.vals)}"

    @staticmethod
    def from_obj(obj: Any) -> "EnumEntry":
        try:
            vals = [EnumValEntry.from_obj(e) for e in obj[K_VALS]]
            return EnumEntry(
                obj[K_DESC],
                obj[K_LABEL],
                vals,
                obj.get(K_NOTES)
            )
        except:
            raise Exception(f"Error parsing enum entry: {obj}")

    @staticmethod
    def to_obj(entry: "EnumEntry") -> Any:
        vals = [EnumValEntry.to_obj(e) for e in entry.vals]
        obj = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_VALS, vals)
        ]
        if entry.notes:
            obj.append((K_NOTES, entry.notes))
        return dict(obj)
