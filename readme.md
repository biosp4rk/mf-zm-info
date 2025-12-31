# Metroid Fusion and Metroid Zero Mission Info Files

## About
These files contain info extracted from the decompilation projects:
- https://github.com/metroidret/mf/
- https://github.com/metroidret/mzm/

The info includes RAM/ROM variables, functions, structs, unions, enums, and typedefs. They're used for the data maps website: http://labk.org/maps/

## Structure
- `json` - Combined YAML files in JSON format; used for the data maps website
- `schema` - JSON schema files used for validating the YAML files
- `sym` - Symbols files for each game and version; can be used with no$gba
- `tools`
  - `decomp` - Scripts for parsing the decompilation projects
  - `dumpers`- Scripts for dumping various types of data, such as OAM or text
  - `info` - Data structures for the extracted info
  - Other notable scripts:
    - `compress.py` - Functions for decompressing RLE and LZ77 compressed data
    - `diff_roms.py` - Script for finding code or data differences between ROMs
    - `function.py` - Class for reading/outputting THUMB functions
    - `references.py` - Script for finding all references to an address
    - `region_find.py` - Script for finding an address from one region in another
    - `sym_file.py` - Script for generating a sym file to use with no$gba
- `yaml` - Info files in YAML format

Game directories are `mf` for Fusion and `zm` for Zero Mission.

For an overview of the info file format, look at the [schema files](schema/) or [info_entry.py](tools/info/info_entry.py).
