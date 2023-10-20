
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
REGION_C = "C"
REGIONS = (REGION_U, REGION_E, REGION_J, REGION_C)

ASM_MODES = ("thumb", "arm")

# entry field keys
K_ADDR = "addr"
K_COUNT = "count"
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
    "palette", "oam_frame",
    "bg_blocks", "bg_map",
    "thumb", "arm"
}
