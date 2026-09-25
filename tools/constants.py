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
BETA_U = "UB"
BETA_E = "EB"

# Fusion has two E betas, 9/11 and 9/16 (they are virtually identical)
MF_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C, BETA_E)
# Zero Mission has two betas, U 12/02 and E 1/14
ZM_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C, BETA_U, BETA_E)

ALL_REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C, "B")

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
