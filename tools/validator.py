import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from constants import *
from game_info import GameInfo
from info_entry import *
import info_file_utils as ifu


SCHEMA_PATH = "../schema"

TYPE_SYMS = {"*", "[", "]", "(", ")"}


class EntryLoc(object):
    def __init__(self):
        self.game: str = None
        self.map_type: str = None
        self.entry_name: str = None
        self.field_name: str = None
    
    def __str__(self) -> str:
        loc = [self.game, self.map_type]
        if self.entry_name:
            loc.append(self.entry_name)
        if self.field_name:
            loc.append(self.field_name)
        return " ".join(loc)

    @staticmethod
    def copy(entry_loc: "EntryLoc") -> "EntryLoc":
        other = EntryLoc()
        other.game = entry_loc.game
        other.map_type = entry_loc.map_type
        other.entry_name = entry_loc.entry_name
        other.field_name = entry_loc.field_name
        return other


class Validator(object):
    def __init__(self):
        self.entry_loc: EntryLoc = EntryLoc()
        self.structs: Dict[str, StructEntry] = None
        self.enums: Dict[str, EnumEntry] = None
        self.errors: List[Tuple[str, EntryLoc]] = []

    def validate(self):
        self.validate_files()
        self.validate_info_entries()

    def validate_files(self) -> None:
        print("Validating files")
        # load schema with shared definitions
        with open(os.path.join(SCHEMA_PATH, "definitions.json")) as f:
            defs_schema = json.load(f)
        defs_resource = Resource.from_contents(defs_schema)
        registry = Registry().with_resource("urn:definitions", defs_resource)

        # go through yaml files of each type
        for map_type in MAP_TYPES:
            self.entry_loc.map_type = map_type
            name = "data" if map_type == "ram" else map_type
            with open(os.path.join(SCHEMA_PATH, name + JSON_EXT)) as f:
                map_schema = json.load(f)
            validator = Draft7Validator(map_schema, registry=registry)

            for game in GAMES:
                paths = ifu.find_yaml_files(game, map_type)
                ylists = ifu.load_yaml_files(paths)
                for path, ylist in zip(paths, ylists):
                    name = os.path.basename(path)
                    print(f"Checking {game} {map_type} {name}")
                    validator.validate(ylist)


    def validate_info_entries(self) -> None:
        print("Validating info entries")
        for game in GAMES:
            self.entry_loc.game = game
            # TODO: some errors can happen when creating GameInfo;
            # consider manually creating each info entry instead
            # (would need to sort and check for overlap at the end)
            info = GameInfo(game, from_json=False)
            self.enums = info.enums
            self.structs = info.structs

            # check enums
            self.entry_loc.map_type = MAP_ENUMS
            for entry in info.enums.values():
                self.entry_loc.entry_name = entry.label
                self.check_vals(entry.vals)

            # check structs
            self.entry_loc.map_type = MAP_STRUCTS
            for entry in info.structs.values():
                self.entry_loc.entry_name = entry.label
                self.check_vars(entry.vars)

            # check code
            self.entry_loc.map_type = MAP_CODE
            prev: CodeEntry = None
            for entry in info.code:
                self.entry_loc.entry_name = entry.label
                self.check_region_int(K_ADDR, entry.addr, 4)
                self.check_region_int(K_SIZE, entry.size, 2)
                self.check_params(entry.params)
                self.check_return(entry.ret)
                self.check_entries_overlap(entry, prev, MAP_CODE)
                prev = entry

            # check data and ram
            data_and_ram = (
                (MAP_DATA, info.data),
                (MAP_RAM, info.ram)
            )
            for map_type, entries in data_and_ram:
                self.entry_loc.map_type = map_type
                prev: DataEntry = None
                for entry in entries:
                    self.entry_loc.entry_name = entry.label
                    valid_type = self.check_type(entry)
                    self.entry_loc.field_name = K_ADDR
                    align = entry.get_alignment(self.structs)
                    self.check_region_int(K_ADDR, entry.addr, align)
                    self.check_enum(entry.enum)
                    if valid_type:
                        # can only check size if type is valid
                        self.check_entries_overlap(entry, prev, map_type)
                        prev = entry
        # print any errors
        if len(self.errors) == 0:
            print("No validation errors")
        else:
            err_cap = 10
            for msg, entry_loc in self.errors[:err_cap]:
                print(entry_loc)
                print(msg)
                print()
            remain = len(self.errors) - err_cap
            if remain > 0:
                print(f"... and {remain} more")

    def add_error(self, message: str) -> None:
        loc = EntryLoc.copy(self.entry_loc)
        self.errors.append((message, loc))

    def check_entries_overlap(self,
        entry: InfoEntry,
        prev: InfoEntry,
        map_type: str
    ) -> None:
        self.entry_loc.field_name = K_ADDR
        if prev is None:
            return
        # get current address
        curr_addr = entry.addr
        if isinstance(curr_addr, int):
            curr_addr = {r: curr_addr for r in REGIONS}
        # get end of previous
        prev_addr = prev.addr
        if isinstance(prev_addr, int):
            prev_addr = {r: prev_addr for r in REGIONS}
        prev_len = None
        if map_type == MAP_CODE:
            prev_len = prev.size
        else:
            prev_len = prev.get_size(self.structs)
        if isinstance(prev_len, int):
            prev_len = {r: prev_len for r in REGIONS}
        prev_end = {
            r: paddr + prev_len[r] - 1
            for r, paddr in prev_addr.items()
        }
        # compare
        for r, a in prev_end.items():
            if r in curr_addr:
                if a >= curr_addr[r]:
                    self.add_error(f"{map_type} entries overlap\n{prev.label}")
                # some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_region_int(self, name: str, entry: RegionInt, align: int) -> None:
        self.entry_loc.field_name = name
        nums = [entry] if isinstance(entry, int) else list(entry.values())
        for num in nums:
            if num % align != 0:
                self.add_error(f"Number must be {align} byte aligned")

    def check_type(self, entry: VarEntry) -> bool:
        self.entry_loc.field_name = K_TYPE
        # check struct
        if (entry.primitive == PrimType.STRUCT and
            entry.struct_name not in self.structs):
            self.add_error("Invalid type")
            return False
        if entry.declaration is None:
            return True
        # check that declaration can be fully parsed
        tokens = tokenize_decl(entry.declaration)
        index = parse_decl(tokens, 0)
        if index != len(tokens):
            self.add_error("Invalid type")
            return False
        return True

    def check_vals(self, vals: List[EnumValEntry]) -> None:
        self.entry_loc.field_name = K_VALS
        prev = -1
        for ve in vals:
            if prev >= ve.val:
                self.add_error("vals should be in ascending order")
            prev = ve.val

    def check_vars(self, vars: List[StructVarEntry]):
        self.entry_loc.field_name = K_VARS
        prev = -1
        for ve in vars:
            self.check_type(ve)
            self.check_enum(ve.enum)
            align = ve.get_alignment(self.structs)        
            self.check_region_int(K_OFFSET, ve.offset, align)
            # TODO: check for overlap
            if prev >= ve.offset:
                self.add_error("offsets should be in ascending order")
            prev = ve.offset

    def check_params(self, params: List[VarEntry]):
        self.entry_loc.field_name = K_PARAMS
        if params is not None:
            for param in params:
                self.check_type(param)
                self.check_enum(param.enum)

    def check_return(self, ret: VarEntry):
        self.entry_loc.field_name = K_RETURN
        if ret is not None:
            self.check_type(ret)
            self.check_enum(ret.enum)

    def check_enum(self, enm: str):
        if enm is None:
            return
        self.entry_loc.field_name = K_ENUM
        if enm not in self.enums:
            self.add_error("Invalid enum")


def tokenize_decl(decl: str):
    tokens = []
    i = 0
    while i < len(decl):
        c = decl[i]
        if c in TYPE_SYMS:
            tokens.append(c)
            i += 1
        elif c == "0" and decl[i + 1] == "x":
            start = i
            i += 2
            while "0" <= decl[i] <= "9" or "A" <= decl[i] <= "F":
                i += 1
            tokens.append(decl[start:i])
        elif "0" <= c <= "9":
            start = i
            while "0" <= decl[i] <= "9":
                i += 1
            tokens.append(decl[start:i])
        else:
            raise AssertionError(f"Unexpected char {c} in type")
    return tokens


def parse_decl(tokens, index: int) -> int:
    # Grammar
    # Decl  -> Ptr Inner Arr | ""
    # Inner -> "(" Decl ")" | ""
    # Ptr   -> "*" Ptr | ""
    # Arr   -> "[" Num "]" Arr | ""
    # Num   -> Dec | Hex
    if index == len(tokens):
        return index
    # check for pointer
    while tokens[index] == "*":
        index += 1
        if index == len(tokens):
            return index
    # check for inner declaration
    if tokens[index] == "(":
        index = parse_decl(tokens, index + 1)
        assert (index < len(tokens) and
            tokens[index] == ")"), f"Expected ) in type"
        index += 1
        if index == len(tokens):
            return index
    # check for arrays
    while tokens[index] == "[":
        assert (index + 1 < len(tokens) and
            tokens[index+1] != "]"), f"Array missing size in type"
        assert (index + 2 < len(tokens) and
            tokens[index+2] == "]"), f"Expected ] in type"
        index += 3
        if index == len(tokens):
            return index
    return index


def output_yamls() -> None:
    # find all yaml files
    yaml_files = []
    for game in GAMES:
        for map_type in MAP_TYPES:
            paths = ifu.find_yaml_files(game, map_type, True)
            yaml_files += [(p, map_type) for p in paths]
    # parse files and output
    for path, map_type in yaml_files:
        data = ifu.load_yaml_file(path)
        ifile = ifu.parse_obj_list(data, map_type)
        ifile.sort()
        ifu.write_info_file(path, map_type, ifile)
    print("Output YAML files")


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # convert each to json
        for map_type in MAP_TYPES:
            data = ifu.get_info_file_from_yaml(game, map_type)
            obj = ifu.info_file_to_obj(map_type, data)
            p = os.path.join(json_dir, map_type + JSON_EXT)
            with open(p, "w") as f:
                json.dump(obj, f, ensure_ascii=False)
    print("Output JSON files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--validate", action="store_true")
    parser.add_argument("-y", "--yaml", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args()

    if len(sys.argv) <= 1:
        parser.print_help()
        quit()
    if args.validate:
        v = Validator()
        v.validate()
    if args.yaml:
        output_yamls()
    if args.json:
        output_jsons()
    print("Done")
