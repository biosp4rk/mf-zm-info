# Metroid Fusion and Metroid Zero Mission Info Files

## About
These files contain labeled RAM and ROM data, along with struct and enum definitions. They're used for the data maps website: http://labk.org/maps/

## Structure
- `yaml` - Info files in YAML format; large files are split for easier editing
- `json` - Combined YAML files in JSON format; used for the data maps website
- `sym` - Symbols files for each game and version; can be used with no$gba
- `tools`
  - `utils.py` - Functions for working with YAML data
  - `validator.py` - Script for validating data and converting to JSON
  - `dumper.py` - Script for finding and outputing data from a ROM file
  - `constants.py` - Defines constants used by other scripts

Game directories are `mf` for Fusion and `zm` for Zero Mission, while `unk` is for unlabeled data.

## Data Format
- ram / rom
  - desc
  - label
  - type
  - addr
  - size (optional)
  - count (optional, assume count=1 if not specified)
  - enum (optional)
- code
  - desc
  - label
  - addr
  - size
  - mode (`thumb` or `arm`)
  - params
  - return
- structs
  - size
  - vars
- enums
  - desc
  - val

### Primitive Types
- `u8` - Unsigned 8 bit integer
- `s8` - Signed 8 bit integer
- `flags8` - 8 bit integer used for bit flags
- `bool` - u8 that only takes values 0 (false) or 1 (true)
- `u16` - Unsigned 16 bit integer
- `s16` - Signed 16 bit integer
- `flags16` - 16 bit integer used for bit flags
- `u32` - Unsigned 32 bit integer
- `s32` - Signed 32 bit integer
- `ptr` - 32 bit pointer to an address
- `ascii` - 8 bit ASCII character
- `char` - 16 bit in-game text character
- `lz` - LZ77 compressed
- `gfx` - Graphics, 32 bytes per tile
- `tilemap` - Tilemap, 2 bytes per tile
- `palette` - Palette, 32 bytes per row
- `thumb` - 16 bit THUMB code
- `arm` - 32 bit ARM code
