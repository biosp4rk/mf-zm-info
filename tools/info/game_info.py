from enum import Enum, auto

from constants import *
from info.asset_type import (
    BUILT_IN_SIZES, TypeSpecKind, AssetType,
    SpecifierType, PointerType, ArrayType, FunctionType
)
from info.info_entry import *
from info.info_file_utils import get_info_file_from_json, get_info_file_from_yaml


class InfoSource(Enum):
    JSON = auto()
    YAML = auto()
    YAML_UNK = auto()


class GameInfo(object):

    def __init__(self,
        game: str,
        region: str = None,
        source: InfoSource = InfoSource.JSON
    ):
        self.game = game
        self.region = region
        if source == InfoSource.JSON:
            self.ram: list[DataEntry] = get_info_file_from_json(game, MAP_RAM, region)
            self.code: list[CodeEntry] = get_info_file_from_json(game, MAP_CODE, region)
            self.data: list[DataEntry] = get_info_file_from_json(game, MAP_DATA, region)
            struct_list: list[StructEntry] = get_info_file_from_json(game, MAP_STRUCTS, region)
            union_list: list[UnionEntry] = get_info_file_from_json(game, MAP_UNIONS, region)
            enum_list: list[EnumEntry] = get_info_file_from_json(game, MAP_ENUMS, region)
            typedef_list: list[TypedefEntry] = get_info_file_from_json(game, MAP_TYPEDEFS, region)
        else:
            include_unk = source == InfoSource.YAML_UNK
            self.ram: list[DataEntry] = get_info_file_from_yaml(game, MAP_RAM, region, include_unk)
            self.code: list[CodeEntry] = get_info_file_from_yaml(game, MAP_CODE, region, include_unk)
            self.data: list[DataEntry] = get_info_file_from_yaml(game, MAP_DATA, region, include_unk)
            struct_list: list[StructEntry] = get_info_file_from_yaml(game, MAP_STRUCTS, region, include_unk)
            union_list: list[UnionEntry] = get_info_file_from_yaml(game, MAP_UNIONS, region, include_unk)
            enum_list: list[EnumEntry] = get_info_file_from_yaml(game, MAP_ENUMS, region, include_unk)
            typedef_list: list[TypedefEntry] = get_info_file_from_yaml(game, MAP_TYPEDEFS, region, include_unk)
        self.structs: dict[str, StructEntry] = {e.name: e for e in struct_list}
        self.unions: dict[str, UnionEntry] = {e.name: e for e in union_list}
        self.enums: dict[str, EnumEntry] = {e.name: e for e in enum_list}
        self.typedefs: dict[str, TypedefEntry] = {e.name: e for e in typedef_list}
        # Get sizes of structs, unions, and typedefs
        self.sizes: dict[str, int] = {}
        for e in struct_list:
            self.sizes[e.name] = e.size
        for e in union_list:
            self.sizes[e.name] = e.size
        for e in typedef_list:
            if e.name not in self.sizes:
                self.sizes[e.name] = self._type_size(e.type)

    def _type_size(self, type: AssetType) -> int:
        """Computes the size of types for the purpose of storing typedef sizes."""
        if isinstance(type, SpecifierType):
            name = type.names[-1]
            if type.kind == TypeSpecKind.BUILT_IN:
                if "long" in type.names:
                    return 8
                size = BUILT_IN_SIZES.get(name)
                if size is not None:
                    return size
                return 4 # int by default
            elif type.kind == TypeSpecKind.TYPEDEF:
                td = self.typedefs.get(name)
                if td is not None:
                    size = self.sizes.get(td.name)
                    if size is None:
                        size = self._type_size(td.type)
                        self.sizes[td.name] = size
                    return size
                else:
                    raise ValueError(f"Unrecognized typedef name {name}")
            elif type.kind == TypeSpecKind.STRUCT:
                return self.sizes[name]
            elif type.kind == TypeSpecKind.UNION:
                return self.sizes[name]
            elif type.kind == TypeSpecKind.ENUM:
                raise ValueError("Can't compute size of enum")
            else:
                raise ValueError(type.kind)
        elif isinstance(type, ArrayType):
            if type.size is None:
                return 0 # treat 0 as unknown
            return type.size * self._type_size(type.inner_type)
        elif isinstance(type, PointerType):
            return 4
        elif isinstance(type, FunctionType):
            raise ValueError("Function types must be pointer")
        else:
            raise ValueError(type)

    def get_enum(self, key: str) -> EnumEntry:
        return self.enums[key]

    def get_struct(self, key: str) -> StructEntry:
        return self.structs[key]

    def get_ram(self, name: str) -> DataEntry:
        for gv in self.ram:
            if gv.name == name:
                return gv
        return None

    def get_code(self, name: str) -> CodeEntry:
        for ce in self.code:
            if ce.name == name:
                return ce
        return None

    def get_data(self, name: str) -> DataEntry:
        for gv in self.data:
            if gv.name == name:
                return gv
        return None

    def get_entry(self, name: str) -> InfoEntry:
        getters = (self.get_ram, self.get_code, self.get_data)
        for getter in getters:
            entry = getter(name)
            if entry is not None:
                return entry
        return None
    
    def get_entry_by_addr(self, addr: int) -> InfoEntry:
        entry_lists = (self.ram, self.code, self.data)
        for entry_list in entry_lists:
            for entry in entry_list:
                if entry.addr == addr:
                    return entry
        return None

    def name_exists(self, name: str) -> bool:
        return self.get_entry(name) is not None
    
    def find_data_by_name(self, tokens: str) -> list[DataEntry]:
        tokens = tokens.lower()
        game_vars: list[DataEntry] = []
        for gv in self.data:
            if tokens in gv.name.lower():
                game_vars.append(gv)
        return game_vars

    def get_data_by_category(self, category: Category) -> list[DataEntry]:
        return [de for de in self.data if de.cat == category]
