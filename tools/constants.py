# Paths and extensions
YAML_PATH = "../yaml"
YAML_EXT = ".yml"
JSON_PATH = "../json"
JSON_EXT = ".json"

# Map types
MAP_CODE = "code"
MAP_DATA = "data"
MAP_ENUMS = "enums"
MAP_RAM = "ram"
MAP_STRUCTS = "structs"
MAP_TYPEDEFS = "typedefs"
MAP_UNIONS = "unions"
MAP_TYPES = (MAP_CODE, MAP_DATA, MAP_ENUMS, MAP_RAM, MAP_STRUCTS, MAP_TYPEDEFS, MAP_UNIONS)

# Game names
GAME_MF = "mf"
GAME_ZM = "zm"
GAMES = (GAME_MF, GAME_ZM)

# Game regions
REGION_U = "U"
REGION_E = "E"
REGION_J = "J"
REGION_C = "C"
# MF
REGION_MF_E_09_11 = "EB"
REGION_MF_E_09_16 = "EB" # Virtually identical to 09/11
MF_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C, REGION_MF_E_09_11)
# ZM
REGION_ZM_U_12_02 = "UB"
REGION_ZM_E_01_14 = "EB"
ZM_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C, REGION_ZM_U_12_02, REGION_ZM_E_01_14)

ALL_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C)

def game_regions(game: str) -> str:
    if game == GAME_MF:
        return MF_REGIONS
    elif game == GAME_ZM:
        return ZM_REGIONS

MODE_THUMB = "thumb"
MODE_ARM = "arm"
ASM_MODES = (MODE_THUMB, MODE_ARM)

# Entry field keys
K_ADDR = "addr"
K_BITS = "bits"
K_CAT = "cat"
K_COMP = "comp"
K_COUNT = "count"
K_DESC = "desc"
K_ENUM = "enum"
K_LOC = "loc"
K_MODE = "mode"
K_NAME = "name"
K_OFFSET = "offset"
K_PARAMS = "params"
K_RETURN = "return"
K_SIZE = "size"
K_TYPE = "type"
K_VAL = "val"
K_VARS = "vars"
K_VALS = "vals"
