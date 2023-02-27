from typing import Dict, List

from constants import *
from info_entry import EnumEntry, StructEntry, DataEntry, CodeEntry, DataTag
from yaml_utils import load_yamls


class GameInfo(object):
    def __init__(self, game: str, region: str = None):
        self.game = game
        self.region = region
        # ram
        ram = load_yamls(game, MAP_RAM, region)
        self.ram: Dict[int, DataEntry] = {e.addr: e for e in ram}
        # code
        code = load_yamls(game, MAP_CODE, region)
        self.code: Dict[int, CodeEntry] = {e.addr: e for e in code}
        # data
        data = load_yamls(game, MAP_DATA, region)
        self.data: Dict[str, DataEntry] = {e.addr: e for e in data}
        # structs + enums
        self.structs: Dict[str, StructEntry] = load_yamls(game, MAP_STRUCTS, region)
        self.enums: Dict[str, EnumEntry] = load_yamls(game, MAP_ENUMS, region)

    def get_enum(self, key: str) -> EnumEntry:
        return self.enums[key]

    def get_struct(self, key: str) -> StructEntry:
        return self.structs[key]

    def label_exists(self, label: str) -> bool:
        for gv in self.ram.values():
            if gv.label == label:
                return True
        for ce in self.code.values():
            if ce.label == label:
                return True
        for gv in self.data.values():
            if gv.label == label:
                return True
        return False
    
    def find_data_by_label(self, tokens: str) -> List[DataEntry]:
        tokens = tokens.lower()
        game_vars: List[DataEntry] = []
        for gv in self.data.values():
            if tokens in gv.label.lower():
                game_vars.append(gv)
        return game_vars

    def get_data_by_tags(self, tags: List[DataTag]) -> List[DataEntry]:
        return [
            de for de in self.data.values()
            if all(t in de.tags for t in tags)
        ]
