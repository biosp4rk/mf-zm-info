from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Union

from constants import *
from info.asset_type import (
    BUILT_IN_SIZES, TypeSpecKind, OuterType, PointerType,
    ArrayType, FunctionType, TypeTokenizer, TypeParser
)


RegionInt = Union[int, dict[str, int]]
"""Type for numbers that can vary by region (addr, size)"""

TOKENIZER = TypeTokenizer()
PARSER = TypeParser()


class Category(Enum):

    BOOL = auto()
    FLAGS = auto()
    ASCII = auto()
    SJIS = auto()
    TEXT = auto()
    GFX = auto()
    TILEMAP = auto()
    PALETTE = auto()
    OAM_FRAME = auto()
    BG_BLOCKS = auto()
    BG_MAP = auto()
    PCM = auto()
    THUMB = auto()
    ARM = auto()

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

    RLE = auto()
    LZ = auto()

COMP_TO_STR = {
    Compression.RLE: "rle",
    Compression.LZ: "lz"
}

STR_TO_COMP = {s: c for c, s in COMP_TO_STR.items()}


class CodeMode(Enum):

    Thumb = auto()
    Arm = auto()

MODE_TO_STR = {
    CodeMode.Thumb: "thumb",
    CodeMode.Arm: "arm"
}

STR_TO_MODE = {s: m for m, s in MODE_TO_STR.items()}


class InfoEntry(ABC):

    def __init__(self, desc: str):
        self.desc = desc

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
        # Get region dictionaries
        addr1 = ri1
        addr2 = ri2
        if isinstance(ri1, int):
            addr1 = {r: ri1 for r in REGIONS}
        if isinstance(ri2, int):
            addr2 = {r: ri2 for r in REGIONS}
        # Compare by first region containing both
        for r in REGIONS:
            if r in addr1 and r in addr2:
                return addr1[r] < addr2[r]
        # Entries are unique to each region,
        # so they're not directly comparable;
        # just compare averages instead
        avg1 = sum(addr1.values()) / len(addr1)
        avg2 = sum(addr2.values()) / len(addr2)
        return avg1 < avg2


class TypedefEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        type: str,
        loc: str
    ):
        super().__init__(desc)
        self.name = name
        tokens = TOKENIZER.tokenize(type)
        self.type = PARSER.parse(tokens)
        self.loc = loc

    def __str__(self) -> str:
        return f"{self.name}"

    def __lt__(self, other: "TypedefEntry") -> bool:
        return self.name < other.name

    @staticmethod
    def from_obj(obj: Any) -> "TypedefEntry":
        return TypedefEntry(
            obj[K_NAME],
            obj.get(K_DESC),
            obj[K_TYPE],
            obj[K_LOC]
        )

    @staticmethod
    def to_obj(entry: "TypedefEntry") -> Any:
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_TYPE, entry.type.decl_str()))
        obj.append((K_LOC, entry.loc))
        return dict(obj)


class VarEntry(InfoEntry):

    def __init__(self,
        desc: str,
        type: str,
        # arr_count of None implies no array
        # arr_count of 1 implies array [1]
        arr_count: RegionInt,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None
    ):
        super().__init__(desc)
        tokens = TOKENIZER.tokenize(type)
        self.type = PARSER.parse(tokens)
        self.arr_count = arr_count
        self.cat = cat
        self.comp = comp
        self.enum = enum

    def __str__(self) -> str:
        return self.type_str()

    def spec_kind(self) -> TypeSpecKind:
        return self.type.spec_kind()

    def spec_names(self) -> list[str]:
        """Returns the base type names (without pointers and arrays)."""
        return self.type.spec_names()

    def spec_name(self) -> str:
        """Returns the last base type name (without pointers and arrays)."""
        return self.type.spec_name()

    def type_str(self) -> str:
        return self.type.decl_str()

    def is_ptr(self) -> bool:
        type = self.type
        while isinstance(type, OuterType):
            if isinstance(type, PointerType):
                return True
            type = type.inner_type

    def has_ptr(self,
        structs: dict[str, "StructEntry"],
        unions: dict[str, "UnionEntry"]
    ) -> bool:
        if self.is_ptr():
            return True
        tk = self.spec_kind()
        if tk == TypeSpecKind.STRUCT:
            se = structs[self.spec_name()]
            if any(v.has_ptr(structs, unions) for v in se.vars):
                return True
        elif tk == TypeSpecKind.UNION:
            ue = unions[self.spec_name()]
            if any(v.has_ptr(structs, unions) for v in ue.vars):
                return True
        return False

    def get_count(self) -> int:
        """Gets the count of the outermost array."""
        if self.arr_count is None:
            return 1
        if isinstance(self.arr_count, dict):
            for r in REGIONS:
                if r in self.arr_count:
                    return self.arr_count[r]
            raise RuntimeError()
        else:
            return self.arr_count

    def get_total_count(self) -> int:
        count = self.get_count()
        type = self.type
        while isinstance(type, OuterType):
            if isinstance(type, ArrayType):
                count *= type.size
            elif isinstance(type, PointerType):
                break
            elif isinstance(type, FunctionType):
                raise RuntimeError()
            type = type.inner_type
        return count

    def get_size(self, sizes: dict[str, int]) -> int:
        """Gets the total size of the entry."""
        spec_size = 4 if self.is_ptr() else self.get_spec_size(sizes)
        return spec_size * self.get_total_count()

    def get_spec_size(self, sizes: dict[str, int]) -> int:
        """Gets the size of a single item of this type."""
        sk = self.spec_kind()
        if sk == TypeSpecKind.BUILT_IN:
            sn = self.spec_names()
            if "long" in sn:
                return 8
            size = BUILT_IN_SIZES.get(sn[-1])
            if size is not None:
                return size
            return 4 # int by default
        elif sk == TypeSpecKind.TYPEDEF or sk == TypeSpecKind.STRUCT or sk == TypeSpecKind.UNION:
            size = sizes.get(self.spec_name())
            if size is not None:
                return size
            ks = sk.name.lower()
            raise ValueError(f"Invalid {ks} name {self.spec_name()}")
        elif sk == TypeSpecKind.ENUM:
            raise ValueError("Can't compute size of enum")
        else:
            raise RuntimeError()

    def get_alignment(self, sizes: dict[str, int]) -> int:
        if self.is_ptr():
            return 4
        tk = self.type.spec_kind()
        # TODO: Determine if unions always have 4 byte alignment
        if tk == TypeSpecKind.STRUCT or tk == TypeSpecKind.UNION:
            return 4
        return self.get_spec_size(sizes)

    @staticmethod
    def from_obj(obj: Any) -> "VarEntry":
        cat = None
        if K_CAT in obj:
            cat = STR_TO_CAT[obj[K_CAT]]
        comp = None
        if K_COMP in obj:
            comp = STR_TO_COMP[obj[K_COMP]]
        return VarEntry(
            obj.get(K_DESC),
            obj[K_TYPE],
            obj.get(K_COUNT),
            cat,
            comp,
            obj.get(K_ENUM)
        )

    @staticmethod
    def to_obj(entry: "VarEntry") -> Any:
        obj = []
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_TYPE, entry.type_str()))
        if entry.arr_count is not None:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        return dict(obj)


class NamedVarEntry(VarEntry):

    def __init__(self,
        name: str,
        desc: str,
        type: str,
        # arr_count of None implies no array
        # arr_count of 1 implies array [1]
        arr_count: RegionInt,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None
    ):
        super().__init__(desc, type, arr_count, cat, comp, enum)
        self.name = name

    @staticmethod
    def from_obj(obj: Any) -> "NamedVarEntry":
        cat = None
        if K_CAT in obj:
            cat = STR_TO_CAT[obj[K_CAT]]
        comp = None
        if K_COMP in obj:
            comp = STR_TO_COMP[obj[K_COMP]]
        return NamedVarEntry(
            obj[K_NAME],
            obj.get(K_DESC),
            obj[K_TYPE],
            obj.get(K_COUNT),
            cat,
            comp,
            obj.get(K_ENUM)
        )

    @staticmethod
    def to_obj(entry: "NamedVarEntry") -> Any:
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_TYPE, entry.type_str()))
        if entry.arr_count is not None:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        return dict(obj)


class DataEntry(NamedVarEntry):

    def __init__(self,
        name: str,
        desc: str,
        type: str,
        arr_count: RegionInt,
        addr: RegionInt,
        loc: str,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None
    ):
        super().__init__(name, desc, type, arr_count, cat, comp, enum)
        self.addr = addr
        self.loc = loc

    def __str__(self) -> str:
        return f"{self.name}"

    def __lt__(self, other: "DataEntry") -> bool:
        return InfoEntry.less_than(self.addr, other.addr)

    def to_region(self, region: str) -> bool:
        # Check addr
        if isinstance(self.addr, dict):
            if region not in self.addr:
                return False
            self.addr = self.addr[region]
        # Check arr_count
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
                obj[K_NAME],
                obj.get(K_DESC),
                obj[K_TYPE],
                obj.get(K_COUNT),
                obj[K_ADDR],
                obj[K_LOC],
                cat,
                comp,
                obj.get(K_ENUM)
            )
        except:
            raise Exception(f"Error parsing data entry: {obj}")

    @staticmethod
    def to_obj(entry: "DataEntry") -> Any:
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_TYPE, entry.type_str()))
        if entry.arr_count is not None:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        obj.append((K_ADDR, entry.addr))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        obj.append((K_LOC, entry.loc))
        return dict(obj)


class StructVarEntry(NamedVarEntry):

    def __init__(self,
        name: str,
        desc: str,
        type: str,
        arr_count: RegionInt,
        offset: RegionInt,
        bits: int = None,
        cat: Category = None,
        comp: Compression = None,
        enum: str = None
    ):
        super().__init__(
            name, desc, type, arr_count, cat, comp, enum
        )
        self.offset = offset
        self.bits = bits

    def __str__(self) -> str:
        return f"{self.offset:X} {self.name}"

    def __lt__(self, other: "StructVarEntry") -> bool:
        return InfoEntry.less_than(self.offset, other.offset)

    def to_region(self, region: str) -> bool:
        # Check offset
        if isinstance(self.offset, dict):
            if region not in self.offset:
                return False
            self.offset = self.offset[region]
        # Check arr_count
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
            obj[K_NAME],
            obj.get(K_DESC),
            obj[K_TYPE],
            obj.get(K_COUNT),
            obj[K_OFFSET],
            obj.get(K_BITS),
            cat,
            comp,
            obj.get(K_ENUM)
        )

    @staticmethod
    def to_obj(entry: "StructVarEntry") -> Any:
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_TYPE, entry.type_str()))
        if entry.arr_count is not None:
            obj.append((K_COUNT, entry.arr_count))
        if entry.cat:
            obj.append((K_CAT, CAT_TO_STR[entry.cat]))
        if entry.comp:
            obj.append((K_COMP, COMP_TO_STR[entry.comp]))
        obj.append((K_OFFSET, entry.offset))
        if entry.bits:
            obj.append((K_BITS, entry.bits))
        if entry.enum:
            obj.append((K_ENUM, entry.enum))
        return dict(obj)


class StructEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        size: int,
        vars: list[StructVarEntry],
        loc: str
    ):
        super().__init__(desc)
        self.name = name
        self.size = size
        self.vars = vars
        self.loc = loc

    def __str__(self) -> str:
        return self.name

    def __lt__(self, other: "StructEntry") -> bool:
        return self.name < other.name

    def get_var(self, name: str) -> StructVarEntry:
        for var in self.vars:
            if var.name == name:
                return var
        return None

    @staticmethod
    def from_obj(obj: Any) -> "StructEntry":
        try:
            vars = [StructVarEntry.from_obj(e) for e in obj[K_VARS]]
            return StructEntry(
                obj[K_NAME],
                obj.get(K_DESC),
                obj[K_SIZE],
                vars,
                obj[K_LOC]
            )
        except:
            raise Exception(f"Error parsing struct entry: {obj}")

    @staticmethod
    def to_obj(entry: "StructEntry") -> Any:
        vars = [StructVarEntry.to_obj(e) for e in entry.vars]
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_SIZE, entry.size))
        obj.append((K_VARS, vars))
        obj.append((K_LOC, entry.loc))
        return dict(obj)


class UnionEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        size: int,
        vars: list[NamedVarEntry],
        loc: str
    ):
        super().__init__(desc)
        self.name = name
        self.size = size
        self.vars = vars
        self.loc = loc

    def __str__(self) -> str:
        return self.name

    def __lt__(self, other: "UnionEntry") -> bool:
        return self.name < other.name

    def get_var(self, name: str) -> NamedVarEntry:
        for var in self.vars:
            if var.name == name:
                return var
        return None

    @staticmethod
    def from_obj(obj: Any) -> "UnionEntry":
        try:
            vars = [NamedVarEntry.from_obj(e) for e in obj[K_VARS]]
            return UnionEntry(
                obj[K_NAME],
                obj.get(K_DESC),
                obj[K_SIZE],
                vars,
                obj[K_LOC]
            )
        except:
            raise Exception(f"Error parsing union entry: {obj}")

    @staticmethod
    def to_obj(entry: "UnionEntry") -> Any:
        vars = [NamedVarEntry.to_obj(e) for e in entry.vars]
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_SIZE, entry.size))
        obj.append((K_VARS, vars))
        obj.append((K_LOC, entry.loc))
        return dict(obj)


class CodeEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        addr: RegionInt,
        size: RegionInt,
        mode: CodeMode,
        params: list[NamedVarEntry],
        ret: VarEntry,
        loc: str
    ):
        super().__init__(desc)
        self.name = name
        self.addr = addr
        self.size = size
        self.mode = mode
        self.params = params
        self.ret = ret
        self.loc = loc

    def __str__(self) -> str:
        return self.name

    def __lt__(self, other: "CodeEntry") -> bool:
        return InfoEntry.less_than(self.addr, other.addr)

    def to_region(self, region: str) -> bool:
        # Check addr
        if isinstance(self.addr, dict):
            if region not in self.addr:
                return False
            self.addr = self.addr[region]
        # Check size
        if isinstance(self.size, dict):
            if region in self.size:
                self.size = self.size[region]
        return True

    def is_thumb(self) -> bool:
        return self.mode == CodeMode.Thumb

    @staticmethod
    def from_obj(obj: Any) -> "CodeEntry":
        try:
            params = [NamedVarEntry.from_obj(p) for p in obj[K_PARAMS]] if obj[K_PARAMS] else None
            ret = VarEntry.from_obj(obj[K_RETURN]) if obj[K_RETURN] else None
            return CodeEntry(
                obj[K_NAME],
                obj.get(K_DESC),
                obj[K_ADDR],
                obj[K_SIZE],
                STR_TO_MODE[obj[K_MODE]],
                params,
                ret,
                obj[K_LOC]
            )
        except:
            raise Exception(f"Error parsing code entry: {obj}")

    @staticmethod
    def to_obj(entry: "CodeEntry") -> Any:
        params = [NamedVarEntry.to_obj(p) for p in entry.params] if entry.params else None
        ret = VarEntry.to_obj(entry.ret) if entry.ret else None
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj += [
            (K_ADDR, entry.addr),
            (K_SIZE, entry.size),
            (K_MODE, MODE_TO_STR[entry.mode]),
            (K_PARAMS, params),
            (K_RETURN, ret),
            (K_LOC, entry.loc)
        ]
        return dict(obj)


class EnumValEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        val: int
    ):
        super().__init__(desc)
        self.name = name
        self.val = val

    def __str__(self) -> str:
        return f"{self.val:X} {self.name}"

    def __lt__(self, other: "EnumValEntry") -> bool:
        return self.val < other.val

    @staticmethod
    def from_obj(obj: Any) -> "EnumValEntry":
        return EnumValEntry(
            obj[K_NAME],
            obj.get(K_DESC),
            obj[K_VAL]
        )

    @staticmethod
    def to_obj(entry: "EnumValEntry") -> Any:
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_VAL, entry.val))
        return dict(obj)


class EnumEntry(InfoEntry):

    def __init__(self,
        name: str,
        desc: str,
        vals: list[EnumValEntry],
        loc: str
    ):
        super().__init__(desc)
        self.name = name
        self.vals = vals
        self.loc = loc

    def __str__(self) -> str:
        return self.name

    def __lt__(self, other: "EnumEntry") -> bool:
        return self.name < other.name

    @staticmethod
    def from_obj(obj: Any) -> "EnumEntry":
        try:
            vals = [EnumValEntry.from_obj(e) for e in obj[K_VALS]]
            return EnumEntry(
                obj[K_NAME],
                obj.get(K_DESC),
                vals,
                obj[K_LOC]
            )
        except:
            raise Exception(f"Error parsing enum entry: {obj}")

    @staticmethod
    def to_obj(entry: "EnumEntry") -> Any:
        vals = [EnumValEntry.to_obj(e) for e in entry.vals]
        obj = [(K_NAME, entry.name)]
        if entry.desc:
            obj.append((K_DESC, entry.desc))
        obj.append((K_VALS, vals))
        obj.append((K_LOC, entry.loc))
        return dict(obj)


NamedEntry = Union[NamedVarEntry, TypedefEntry, StructEntry, UnionEntry, EnumEntry]
