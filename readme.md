# Metroid Fusion and Metroid Zero Mission Info Files

## About
These files contain labeled RAM and ROM data, along with struct and enum definitions. They're used for the data maps website: http://labk.org/maps/

## Structure
- `json` - Combined YAML files in JSON format; used for the data maps website
- `sym` - Symbols files for each game and version; can be used with no$gba
- `tools`
  - `compress.py` - Functions for decompressing RLE and LZ77 compressed data
  - `constants.py` - Defines constants used by other scripts
  - `dumper.py` - Script for finding and outputting data from a ROM file
  - `function.py` - Class for reading/outputting THUMB functions
  - `game_info.py` - Class for handling all info entries for a game
  - `info_entry.py` - Classes for representing info entries of each type
  - `references.py` - Script for finding all references to an address
  - `region_find.py` - Script for finding an address from one region in another
  - `rom.py` - Class for handling a Fusion or Zero Mission ROM file
  - `sym_file.py` - Script for generating a sym file to use with no$gba
  - `symbols.py` - Class for storing labels while disassembling functions
  - `thumb.py` - Class for representing THUMB instructions
  - `validator.py` - Script for validating data and converting to JSON
  - `yaml_utils.py` - Functions for working with YAML data
- `yaml` - Info files in YAML format; large files are split for easier editing

Game directories are `mf` for Fusion and `zm` for Zero Mission. Files starting with `unk` are for unlabeled data.

## Data Format

### Type Definitions

- `hex` is a hexadecimal string that matches the pattern `0x[0-9A-F]+`
- Labels must match the pattern `[A-Za-z]\w*`
- `Region = Literal['U', 'E', 'J']`
- `RegionDict = Dict[Region, hex]`
- `RegionInt = Union[hex, RegionDict]`

### Entry Attributes

- GameEntry
  - **`desc`** : `str`
  - **`label`** : `str`
  - **`notes`** : `Optional[str]`
- GameVar (extends GameEntry)
  - **`type`** : `str`
  - **`count`** : `RegionInt`
  - **`tags`** : `Optional[List[str]]`
  - **`enum`** : `Optional[str]`
- RAM / ROM (extends GameVar)
  - **`addr`** : `RegionInt`
- Code (extends GameEntry)
  - **`addr`** : `RegionInt`
  - **`size`** : `RegionInt`
  - **`mode`** : `Literal['thumb', 'arm']`
  - **`params`** : `Union[List[GameVar], None]`
  - **`return`** : `Union[GameVar, None]`
- Struct (extends GameEntry)
  - **`size`** : `hex`
  - **`vars`** : `List` (Extends GameVar)
    - **`offset`** : `hex`
- Enum (extends GameEntry)
  - **`vals`**: `List`
    - **`desc`** : `str`
    - **`label`** : `str`
    - **`val`** : `hex`
    - **`notes`** : `Optional[str]`

### Primitive Types
- `u8` - Unsigned 8 bit integer
- `s8` - Signed 8 bit integer
- `bool` - u8 that only takes values 0 (false) or 1 (true)
- `u16` - Unsigned 16 bit integer
- `s16` - Signed 16 bit integer
- `u32` - Unsigned 32 bit integer
- `s32` - Signed 32 bit integer

### Categories
- `flags` - Integer used for bit flags
- `ascii` - 8 bit ASCII character
- `sjis` - 8 bit Shift JIS character
- `text` - 16 bit in-game text character
- `gfx` - Graphics, 32 bytes per tile
- `tilemap` - Tilemap, 2 bytes per tile
- `palette` - Palette, 32 bytes per row
- `oam_frame` - OAM frame, 16 bit attributes
- `bg_blocks` - Block map for a background (RLE)
- `bg_map` - Tilemap for a background (LZ77)
- `pcm` - Pulse-code modulation audio sample
- `thumb` - 16 bit THUMB code
- `arm` - 32 bit ARM code

### Compression
- `rle` - RLE compressed
- `lz` - LZ77 compressed

### Label Abbreviations
- `Alt` - Alternate
- `Anim` - Animation
- `BG` - Background
- `Calc` - Calculate
- `Curr` - Current
- `Def` - Definition
- `Gfx` - Graphics
- `Init` - Initialize
- `Nav` - Navigation
- `Num` - Number
- `Prev` - Previous
- `Ptr` - Pointer
- `Unk` - Unknown
