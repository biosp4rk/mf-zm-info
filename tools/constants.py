
# paths and extensions
YAML_PATH = "../yaml"
YAML_EXT = ".yml"
JSON_PATH = "../json"
JSON_EXT = ".json"

# map types
MAP_CODE = "code"
MAP_DATA = "data"
MAP_ENUMS = "enums"
MAP_RAM = "ram"
MAP_STRUCTS = "structs"
MAP_TYPES = (MAP_CODE, MAP_DATA, MAP_ENUMS, MAP_RAM, MAP_STRUCTS)

# game names
GAME_MF = "mf"
GAME_ZM = "zm"
GAMES = (GAME_MF, GAME_ZM)

# game regions
REGION_U = "U"
REGION_E = "E"
REGION_J = "J"
#REGION_C = "c"
REGIONS = (REGION_U, REGION_E, REGION_J)
#REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C)

ASM_MODES = ("thumb", "arm")

# entry field keys
K_ADDR = "addr"
K_DESC = "desc"
K_ENUM = "enum"
K_LABEL = "label"
K_MODE = "mode"
K_NOTES = "notes"
K_OFFSET = "offset"
K_PARAMS = "params"
K_RETURN = "return"
K_SIZE = "size"
K_TAGS = "tags"
K_TYPE = "type"
K_VAL = "val"
K_VARS = "vars"
K_VALS = "vals"

# entry valid fields
# fields are in preferred output order
DATA = (
    K_DESC,
    K_LABEL,
    K_TYPE,
    K_TAGS,
    K_ADDR,
    K_ENUM,
    K_NOTES
)
CODE_VAR = (
    K_DESC,
    K_LABEL,
    K_TYPE,
    K_TAGS,
    K_ENUM,
    K_NOTES
)
FIELDS = {
    MAP_ENUMS: (
        K_DESC,
        K_LABEL,
        K_VAL,
        K_NOTES
    ),
    MAP_STRUCTS: (
        K_SIZE,
        K_VARS
    ),
    MAP_CODE: (
        K_DESC,
        K_LABEL,
        K_ADDR,
        K_SIZE,
        K_MODE,
        K_PARAMS,
        K_RETURN,
        K_NOTES
    ),
    MAP_RAM: DATA,
    MAP_DATA: DATA,
    K_ADDR: REGIONS,
    K_SIZE: REGIONS,
    K_VARS:  (
        K_DESC,
        K_LABEL,
        K_TYPE,
        K_TAGS,
        K_OFFSET,
        K_ENUM,
        K_NOTES
    ),
    K_PARAMS: CODE_VAR,
    K_RETURN: CODE_VAR
}

# primitive type sizes
PRIMITIVES = {
    "void": 1,
    "u8": 1,
    "s8": 1,
    "bool": 1,
    "u16": 2,
    "s16": 2,
    "u32": 4,
    "s32": 4
}

# valid strings for tags field
TAGS = {
    "flags", "ascii", "text",
    "rle", "lz", "gfx", "tilemap",
    "palette", "oamframe",
    "bg_blocks", "bg_map",
    "thumb", "arm"
}
