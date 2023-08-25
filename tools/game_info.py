from typing import Dict, List

from constants import *
from info_entry import InfoEntry, EnumEntry, StructEntry, DataEntry, CodeEntry, DataTag
from yaml_utils import load_info_files


class GameInfo(object):
    def __init__(self, game: str, region: str = None):
        self.game = game
        self.region = region 
        self.ram: List[DataEntry] = load_info_files(game, MAP_RAM, region)
        self.code: List[CodeEntry] = load_info_files(game, MAP_CODE, region)
        self.data: List[DataEntry] = load_info_files(game, MAP_DATA, region)
        struct_list = load_info_files(game, MAP_STRUCTS, region)
        self.structs: Dict[str, StructEntry] = {e.label: e for e in struct_list}
        enum_list = load_info_files(game, MAP_ENUMS, region)
        self.enums: Dict[str, EnumEntry] = {e.label: e for e in enum_list}

    def get_enum(self, key: str) -> EnumEntry:
        return self.enums[key]

    def get_struct(self, key: str) -> StructEntry:
        return self.structs[key]

    def get_ram(self, label: str) -> DataEntry:
        for gv in self.ram:
            if gv.label == label:
                return gv
        return None

    def get_code(self, label: str) -> CodeEntry:
        for ce in self.code:
            if ce.label == label:
                return ce
        return None

    def get_data(self, label: str) -> DataEntry:
        for gv in self.data:
            if gv.label == label:
                return gv
        return None

    def get_entry(self, label: str) -> InfoEntry:
        getters = (self.get_ram, self.get_code, self.get_data)
        for getter in getters:
            entry = getter(label)
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

    def label_exists(self, label: str) -> bool:
        return self.get_entry(label) is not None
    
    def find_data_by_label(self, tokens: str) -> List[DataEntry]:
        tokens = tokens.lower()
        game_vars: List[DataEntry] = []
        for gv in self.data:
            if tokens in gv.label.lower():
                game_vars.append(gv)
        return game_vars

    def get_data_by_tags(self, tags: List[DataTag]) -> List[DataEntry]:
        return [
            de for de in self.data
            if all(t in de.tags for t in tags)
        ]
