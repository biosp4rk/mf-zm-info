import argparse
import json
import os
import sys
from typing import Union

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from constants import *
from info.asset_type import AssetType, OuterType, PointerType, FunctionType
from info.game_info import GameInfo, InfoSource
from info.info_entry import *
import info.info_file_utils as ifu


SCHEMA_PATH = "../schema"


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
        self.info: GameInfo = None
        self.errors: list[tuple[str, EntryLoc]] = []

    def validate(self):
        self.validate_files()
        self.validate_info_entries()

    def validate_files(self) -> None:
        print("Validating files")
        # Load schema with shared definitions
        with open(os.path.join(SCHEMA_PATH, "definitions.json")) as f:
            defs_schema = json.load(f)
        defs_resource = Resource.from_contents(defs_schema)
        registry = Registry().with_resource("urn:definitions", defs_resource)

        # Go through yaml files of each type
        for map_type in MAP_TYPES:
            self.entry_loc.map_type = map_type
            name = MAP_DATA if map_type == MAP_RAM else map_type
            with open(os.path.join(SCHEMA_PATH, name + JSON_EXT)) as f:
                map_schema = json.load(f)
            validator = Draft7Validator(map_schema, registry=registry)

            for game in GAMES:
                paths = ifu.find_yaml_files(game, map_type, True)
                ylists = ifu.load_yaml_files(paths)
                for path, ylist in zip(paths, ylists):
                    name = os.path.basename(path)
                    print(f"Checking {game} {map_type} {name}")
                    validator.validate(ylist)


    def validate_info_entries(self) -> None:
        print("Validating info entries")
        for game in GAMES:
            self.entry_loc.game = game
            # TODO: Some errors can happen when creating GameInfo;
            # consider manually creating each info entry instead
            # (would need to sort and check for overlap at the end)
            self.info = GameInfo(game, source=InfoSource.YAML_UNK)

            # Check typedefs
            self.entry_loc.map_type = MAP_TYPEDEFS
            for entry in self.info.typedefs.values():
                self.check_type(entry.type)

            # Check enums
            self.entry_loc.map_type = MAP_ENUMS
            for entry in self.info.enums.values():
                self.entry_loc.entry_name = entry.name
                self.check_enum_vals(entry.vals)

            # Check structs
            self.entry_loc.map_type = MAP_STRUCTS
            for entry in self.info.structs.values():
                self.entry_loc.entry_name = entry.name
                self.check_struct_vars(entry.vars)
            
            # Check unions
            self.entry_loc.map_type = MAP_UNIONS
            for entry in self.info.unions.values():
                self.entry_loc.entry_name = entry.name
                self.check_union_vars(entry.vars)

            # Check code
            self.entry_loc.map_type = MAP_CODE
            prev: CodeEntry = None
            for entry in self.info.code:
                self.entry_loc.entry_name = entry.name
                self.check_region_int(K_ADDR, entry.addr, 4)
                self.check_region_int(K_SIZE, entry.size, 2)
                self.check_params(entry.params)
                self.check_return(entry.ret)
                self.check_entries_overlap(entry, prev, MAP_CODE)
                prev = entry

            # Check data and ram
            data_and_ram: list[tuple[str, list[DataEntry]]] = [
                (MAP_DATA, self.info.data), (MAP_RAM, self.info.ram)
            ]
            for map_type, entries in data_and_ram:
                self.entry_loc.map_type = map_type
                prev: DataEntry = None
                for entry in entries:
                    self.entry_loc.entry_name = entry.name
                    valid_type = self.check_type(entry.type)
                    self.entry_loc.field_name = K_ADDR
                    align = entry.get_alignment(self.info.sizes)
                    self.check_region_int(K_ADDR, entry.addr, align)
                    self.check_enum(entry.enum)
                    if valid_type:
                        # Can only check size if type is valid
                        self.check_entries_overlap(entry, prev, map_type)
                        prev = entry
        # Print any errors
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
        entry: Union[DataEntry, CodeEntry],
        prev: Union[DataEntry, CodeEntry],
        map_type: str
    ) -> None:
        self.entry_loc.field_name = K_ADDR
        if prev is None:
            return
        # Get current address
        curr_addr = entry.addr
        if isinstance(curr_addr, int):
            curr_addr = {r: curr_addr for r in ALL_REGIONS}
        # Get end of previous
        prev_addr = prev.addr
        if isinstance(prev_addr, int):
            prev_addr = {r: prev_addr for r in ALL_REGIONS}
        prev_len = None
        if map_type == MAP_CODE:
            prev_len = prev.size
        else:
            prev_len = prev.get_size(self.info.sizes)
        if isinstance(prev_len, int):
            prev_len = {r: prev_len for r in ALL_REGIONS}
        prev_end = {
            r: paddr + prev_len[r] - 1
            for r, paddr in prev_addr.items()
        }
        # Compare
        for r, a in prev_end.items():
            if r in curr_addr:
                if a >= curr_addr[r]:
                    self.add_error(f"{map_type} entries overlap\n{prev.name}")
                # Some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_region_int(self, name: str, entry: RegionInt, align: int) -> None:
        self.entry_loc.field_name = name
        nums = [entry] if isinstance(entry, int) else list(entry.values())
        for num in nums:
            if num % align != 0:
                self.add_error(f"Number must be {align} byte aligned")

    def check_type(self, type: AssetType) -> bool:
        self.entry_loc.field_name = K_TYPE
        # Check struct, union, or typedef
        tk = type.spec_kind()
        entry_dict: dict[str, Any] = None
        if tk == TypeSpecKind.STRUCT:
            entry_dict = self.info.structs
        elif tk == TypeSpecKind.UNION:
            entry_dict = self.info.unions
        elif tk == TypeSpecKind.TYPEDEF:
            entry_dict = self.info.typedefs
        if entry_dict is not None and type.spec_name() not in entry_dict:
            self.add_error(f"Invalid {tk.name.lower()} type {type.spec_name()}")
            return False
        # Check for non-pointer functions
        prev_type: AssetType = None
        while isinstance(type, OuterType):
            if (
                isinstance(type, FunctionType) and
                not isinstance(prev_type, PointerType)
            ):
                self.add_error("Functions must be pointers")
                return False
            prev_type = type
            type = type.inner_type
        return True

    def check_enum_vals(self, vals: list[EnumValEntry]) -> None:
        self.entry_loc.field_name = K_VALS
        prev = -1
        for ve in vals:
            if prev > ve.val:
                self.add_error("vals should be in ascending order")
            prev = ve.val

    def check_struct_vars(self, vars: list[StructVarEntry]):
        self.entry_loc.field_name = K_VARS
        prev = -1
        for ve in vars:
            self.check_type(ve.type)
            self.check_enum(ve.enum)
            if ve.bits is None:
                align = ve.get_alignment(self.info.sizes)
            else:
                align = 1
            self.check_region_int(K_OFFSET, ve.offset, align)
            # TODO: Check for overlap
            if prev > ve.offset:
                self.add_error("offsets should be in ascending order")
            prev = ve.offset

    def check_union_vars(self, vars: list[NamedVarEntry]):
        self.entry_loc.field_name = K_VARS
        for ve in vars:
            self.check_type(ve.type)
            self.check_enum(ve.enum)

    def check_params(self, params: list[NamedVarEntry]):
        self.entry_loc.field_name = K_PARAMS
        if params is not None:
            for param in params:
                self.check_type(param.type)
                self.check_enum(param.enum)

    def check_return(self, ret: VarEntry):
        self.entry_loc.field_name = K_RETURN
        if ret is not None:
            self.check_type(ret.type)
            self.check_enum(ret.enum)

    def check_enum(self, enm: str):
        if enm is None:
            return
        self.entry_loc.field_name = K_ENUM
        if enm not in self.info.enums:
            self.add_error("Invalid enum")


def output_yamls() -> None:
    # Find all yaml files
    yaml_files = []
    for game in GAMES:
        for map_type in MAP_TYPES:
            paths = ifu.find_yaml_files(game, map_type, True)
            yaml_files += [(p, map_type) for p in paths]
    # Parse files and output
    for path, map_type in yaml_files:
        data = ifu.load_yaml_file(path)
        ifile = ifu.parse_obj_list(data, map_type)
        ifile.sort()
        ifu.write_info_file(path, map_type, ifile)
    print("Output YAML files")


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # Convert each to json
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
