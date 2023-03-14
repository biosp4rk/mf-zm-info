from enum import Enum
import re
from typing import Any, Dict, List, Union

from constants import *


# type for numbers that can vary by region (addr, size)
RegionInt = Union[int, Dict[str, int]]


class PrimType(Enum):
    U8 = 1
    S8 = 2
    Bool = 3
    U16 = 4
    S16 = 5
    U32 = 6
    S32 = 7
    Struct = 8
    Void = 9


class DataTag(Enum):
    Flags = 1
    Ascii = 2
    Text = 3
    Rle = 4
    LZ = 5
    Gfx = 6
    Tilemap = 7
    Palette = 8
    OamFrame = 9
    BGBlocks = 10
    BGMap = 11
    Thumb = 12
    Arm = 13

TAG_TO_STR = {
    DataTag.Flags: "flags",
    DataTag.Ascii: "ascii",
    DataTag.Text: "text",
    DataTag.Rle: "rle",
    DataTag.LZ: "lz",
    DataTag.Gfx: "gfx",
    DataTag.Tilemap: "tilemap",
    DataTag.Palette: "palette",
    DataTag.OamFrame: "oam_frame",
    DataTag.BGBlocks: "bg_blocks",
    DataTag.BGMap: "bg_map",
    DataTag.Thumb: "thumb",
    DataTag.Arm: "arm"
}

STR_TO_TAG = {s: t for t, s in TAG_TO_STR.items()}


class CodeMode(Enum):
    Thumb = 1
    Arm = 2


class InfoEntry(object):

    def __init__(self, desc: str, label: str, notes: str = None):
        self.desc = desc
        self.label = label  
        self.notes = notes      

    def __lt__(self, other: "InfoEntry") -> bool:
        return self.label < other.label

    def to_region(self, region: str) -> bool:
        return True

    @staticmethod
    def from_yaml(node: Any) -> "InfoEntry":
        raise NotImplementedError()

    @staticmethod
    def to_yaml(entry: "InfoEntry") -> Any:
        raise NotImplementedError()

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
        tags: List[DataTag] = [],
        enum: str = None,
        notes: str = None
    ):
        super().__init__(desc, label, notes)
        self.parse_type(type)
        self.arr_count = arr_count
        self.tags = tags
        self.enum = enum

    def __str__(self) -> str:
        return self.label

    def parse_type(self, type: str):
        parts = type.split()
        # primitive
        prim = parts[0]
        prim = prim[0].upper() + prim[1:]
        pt = None
        try:
            # TODO: use dictionary of strings instead
            pt = PrimType[prim]
        except KeyError:
            pt = None
        if pt is not None:
            self.primitive = pt
            self.struct_name = None
        else:
            self.primitive = PrimType.Struct
            self.struct_name = prim
        # declaration
        if len(parts) == 2:
            self.declaration = parts[1]
        else:
            self.declaration = None

    def spec(self) -> str:
        if self.primitive == PrimType.Struct:
            return self.struct_name
        # TODO: use dictionary instead
        return self.primitive.name.lower()

    def type_str(self) -> str:
        if self.declaration is None:
            return self.spec()
        return f"{self.spec()} {self.declaration}"

    def is_ptr(self) -> bool:
        return self.declaration.startswith("*")

    def get_count(self) -> int:
        if self.arr_count is None:
            return 1
        if isinstance(self.arr_count, dict):
            for r in REGIONS:
                if r in self.arr_count:
                    return self.arr_count[r]
        else:
            return self.arr_count

    def get_size(self, structs: Dict[str, "StructEntry"]) -> int:
        size = self.get_spec_size(structs)
        if self.declaration is not None:
            # get inner-most part of declaration
            decl = self.declaration
            i = decl.rfind("(")
            if i != -1:
                i += 1
                j = decl.find(")")
                decl = decl[i:j]
            # check for pointer
            if decl.startswith("*"):
                size = 4
                decl = decl.lstrip("*")
            # check for array
            mc = re.findall(r"\w+", decl)
            for m in mc:
                dim = int(m, 16)
                size *= dim
        return size * self.get_count()

    def get_spec_size(self, structs: Dict[str, "StructEntry"]) -> int:
        if self.primitive in {
            PrimType.Void,
            PrimType.U8,
            PrimType.S8,
            PrimType.Bool
        }:
            return 1
        elif (self.primitive == PrimType.U16 or
            self.primitive == PrimType.S16):
            return 2
        elif (self.primitive == PrimType.U32 or
            self.primitive == PrimType.S32):
            return 4
        elif self.primitive == PrimType.Struct:
            se = structs.get(self.struct_name)
            if se is not None:
                return se.size
            msg = f"Invalid struct name {self.struct_name}"
            raise ValueError(msg)

    @staticmethod
    def from_yaml(node: Any) -> "VarEntry":
        assert isinstance(node, dict)
        return VarEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_TYPE],
            node.get(K_COUNT),
            VarEntry.tags_from_yaml(node.get(K_TAGS)),
            node.get(K_ENUM),
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "VarEntry") -> str:
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            data.append((K_COUNT, entry.arr_count))
        if entry.tags:
            data.append((K_TAGS, VarEntry.tags_to_yaml(entry.tags)))
        if entry.enum:
            data.append((K_ENUM, entry.enum))
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)
    
    @staticmethod
    def tags_from_yaml(tags: List[str]) -> List[DataTag]:
        if tags is None:
            return None
        return [STR_TO_TAG[s] for s in tags]

    @staticmethod
    def tags_to_yaml(tags: List[DataTag]) -> List[str]:
        if tags is None:
            return None
        return [TAG_TO_STR[t] for t in tags]


class DataEntry(VarEntry):

    def __init__(self,
        desc: str,
        label: str,
        type: str,
        arr_count: RegionInt,
        addr: RegionInt,
        tags: List[DataTag] = [],
        enum: str = None,
        notes: str = None
    ):
        super().__init__(desc, label, type, arr_count, tags, enum, notes)
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
    def from_yaml(node: Any) -> "DataEntry":
        assert isinstance(node, dict)
        return DataEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_TYPE],
            node.get(K_COUNT),
            node[K_ADDR],
            VarEntry.tags_from_yaml(node.get(K_TAGS)),
            node.get(K_ENUM),
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "DataEntry") -> Any:
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            data.append((K_COUNT, entry.arr_count))
        if entry.tags:
            data.append((K_TAGS, VarEntry.tags_to_yaml(entry.tags)))
        data.append((K_ADDR, entry.addr))
        if entry.enum:
            data.append((K_ENUM, entry.enum))
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)


class StructVarEntry(VarEntry):

    def __init__(self,
        desc: str,
        label: str,
        type: str,
        arr_count: RegionInt,
        offset: RegionInt,
        tags: List[DataTag] = [],
        enum: str = None,
        notes: str = None
    ):
        super().__init__(desc, label, type, arr_count, tags, enum, notes)
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
    def from_yaml(node: Any) -> "StructVarEntry":
        assert isinstance(node, dict)
        return StructVarEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_TYPE],
            node.get(K_COUNT),
            node[K_OFFSET],
            VarEntry.tags_from_yaml(node.get(K_TAGS)),
            node.get(K_ENUM),
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "StructVarEntry") -> Any:
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_TYPE, entry.type_str())
        ]
        if entry.arr_count:
            data.append((K_COUNT, entry.arr_count))
        if entry.tags:
            data.append((K_TAGS, VarEntry.tags_to_yaml(entry.tags)))
        data.append((K_OFFSET, entry.offset))
        if entry.enum:
            data.append((K_ENUM, entry.enum))
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)


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

    @staticmethod
    def from_yaml(node: Any) -> "StructEntry":
        assert isinstance(node, dict)
        vars = [StructVarEntry.from_yaml(e) for e in node[K_VARS]]
        return StructEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_SIZE],
            vars,
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "StructEntry") -> Any:
        vars = [StructVarEntry.to_yaml(e) for e in entry.vars]
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_SIZE, entry.size),
            (K_VARS, vars)
        ]
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)


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
    def from_yaml(node: Any) -> "CodeEntry":
        assert isinstance(node, dict)
        mode = CodeMode.Arm if node[K_MODE] == "arm" else CodeMode.Thumb
        params = node[K_PARAMS]
        # TODO: don't allow str for params
        if not isinstance(params, str):
            params = [VarEntry.from_yaml(p) for p in params] if params else None
        ret = node[K_RETURN]
        # TODO: don't allow str for return
        if not isinstance(ret, str):
            ret = VarEntry.from_yaml(ret) if ret else None
        return CodeEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_ADDR],
            node[K_SIZE],
            mode,
            params,
            ret,
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "CodeEntry") -> Any:
        mode = "arm" if entry.mode == CodeMode.Arm else "thumb"
        # TODO: don't allow str for params
        params = entry.params
        if not isinstance(entry.params, str):
            params = [VarEntry.to_yaml(p) for p in entry.params] if entry.params else None
        # TODO: don't allow str for return
        ret = entry.ret
        if not isinstance(entry.ret, str):
            ret = VarEntry.to_yaml(entry.ret) if entry.ret else None
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_ADDR, entry.addr),
            (K_SIZE, entry.size),
            (K_MODE, mode),
            (K_PARAMS, params),
            (K_RETURN, ret),
        ]
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)


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
    def from_yaml(node: Any) -> "EnumValEntry":
        assert isinstance(node, dict)
        return EnumValEntry(
            node[K_DESC],
            node[K_LABEL],
            node[K_VAL],
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "EnumValEntry") -> Any:
        data = [
            ("desc", entry.desc),
            ("label", entry.label),
            ("val", entry.val)
        ]
        if entry.notes:
            data.append(("notes", entry.notes))
        return dict(data)


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
    def from_yaml(node: Any) -> "EnumEntry":
        assert isinstance(node, dict)
        vals = [EnumValEntry.from_yaml(e) for e in node[K_VALS]]
        return EnumEntry(
            node[K_DESC],
            node[K_LABEL],
            vals,
            node.get(K_NOTES)
        )

    @staticmethod
    def to_yaml(entry: "EnumEntry") -> Any:
        vals = [EnumValEntry.to_yaml(e) for e in entry.vals]
        data = [
            (K_DESC, entry.desc),
            (K_LABEL, entry.label),
            (K_VALS, vals)
        ]
        if entry.notes:
            data.append((K_NOTES, entry.notes))
        return dict(data)
