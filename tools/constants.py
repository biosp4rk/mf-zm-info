from typing import Dict, Union


YAML_PATH = "../yaml"
YAML_EXT = ".yml"
JSON_PATH = "../json"
JSON_EXT = ".json"

MAP_CODE = "code"
MAP_DATA = "data"
MAP_ENUMS = "enums"
MAP_RAM = "ram"
MAP_STRUCTS = "structs"
MAP_TYPES = (MAP_CODE, MAP_DATA, MAP_ENUMS, MAP_RAM, MAP_STRUCTS)

GAME_MF = "mf"
GAME_ZM = "zm"
GAMES = (GAME_MF, GAME_ZM)

REGION_U = "U"
REGION_E = "E"
REGION_J = "J"
#REGION_C = "C"
REGIONS = (REGION_U, REGION_E, REGION_J)
#REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C)

ASM_MODES = ("thumb", "arm")

DATA = (
    "label",
    "type",
    "addr",
    "size",
    "count",
    "enum",
    "notes"
)
CODE_VAR = ("label", "type", "enum", "notes")
FIELDS = {
    MAP_ENUMS: (
        "label",
        "val",
        "notes"
    ),
    MAP_STRUCTS: (
        "size",
        "vars"
    ),
    MAP_CODE: (
        "label",
        "addr",
        "size",
        "mode",
        "params",
        "return",
        "notes"
    ),
    MAP_RAM: DATA,
    MAP_DATA: DATA,
    "addr": REGIONS,
    "size": REGIONS,
    "count": REGIONS,
    "vars":  (
        "label",
        "type",
        "offset",
        "size",
        "count",
        "enum",
        "notes"
    ),
    "params": CODE_VAR,
    "return": CODE_VAR
}

PRIMITIVES = {
    "u8": 1,
    "s8": 1,
    "bool": 1,
    "u16": 2,
    "s16": 2,
    "u32": 4,
    "s32": 4
}

TAGS = {
    "flags", "ascii", "text",
    "rle", "lz", "gfx", "tilemap",
    "palette", "oamframe",
    "thumb", "arm"
}

RegionInt = Union[int, Dict[str, int]]
