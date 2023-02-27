import argparse
import json
import os
import re
import sys
from typing import Dict, List, Tuple

from constants import *
from game_info import GameInfo
from info_entry import *
from yaml_utils import load_yaml, load_yamls


LABEL_PAT = re.compile(r"^[A-Za-z]\w*$", flags=re.A)

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
        for game in GAMES:
            self.entry_loc.game = game
            # get all info
            info = GameInfo(game)
            self.enums = info.enums
            self.structs = info.structs

            # check enums
            self.entry_loc.map_type = MAP_ENUMS
            for key, en in self.enums.items():
                self.entry_loc.entry_name = key
                self.check_label(key)
                self.check_vals(en.vals)

            # check structs
            self.entry_loc.map_type = MAP_STRUCTS
            for key, st in self.structs.items():
                self.entry_loc.entry_name = key
                self.check_label(key)
                self.entry_loc.field_name = K_SIZE
                self.check_region_int(st.size)
                self.check_vars(st.vars)

            # check code
            self.entry_loc.map_type = MAP_CODE
            prev: CodeEntry = None
            for entry in info.code:
                self.entry_loc.entry_name = entry.label
                self.check_desc(entry.desc)
                self.check_label(entry.label)
                self.entry_loc.field_name = K_ADDR
                self.check_region_int(entry.addr, 4)
                self.entry_loc.field_name = K_SIZE
                self.check_region_int(entry.size, 2)
                self.check_mode(entry.mode)
                self.check_params(entry.params)
                self.check_return(entry.ret)
                self.check_notes(entry.notes)
                self.check_code_overlap(entry, prev)
                prev = entry

            # check data and ram
            ram_rom: Tuple[Tuple[str, List[DataEntry]]] = (
                (MAP_DATA, info.data),
                (MAP_RAM, info.ram)
            )
            for map_type, entries in ram_rom:
                self.entry_loc.map_type = map_type
                prev: DataEntry = None
                for entry in entries:
                    self.entry_loc.entry_name = entry.label
                    self.check_desc(entry.desc)
                    self.check_label(entry.label)
                    self.check_decl(entry.declaration)
                    self.check_tags(entry.tags)
                    self.entry_loc.field_name = K_ADDR
                    align = None
                    if entry.primitive != PrimType.Struct:
                        align = entry.get_spec_size(self.structs)
                    self.check_region_int(entry.addr, align)
                    self.check_enum(entry.enum)
                    self.check_notes(entry.notes)
                    self.check_data_overlap(entry, prev)
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

    # TODO: combined shared code with check_code_overlap
    def check_data_overlap(self, entry: DataEntry, prev: DataEntry) -> None:
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
        prev_len = prev.size(self.structs)
        for r in prev_addr:
            prev_addr[r] += prev_len - 1
        # compare
        for r, a in prev_addr.items():
            if r in curr_addr:
                if a >= curr_addr[r]:
                    self.add_error(f"data entries overlap\n{prev.label}")
                # some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_code_overlap(self, entry: CodeEntry, prev: CodeEntry) -> None:
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
        prev_len = prev.size
        if isinstance(prev_len, int):
            prev_len = {r: prev_len for r in REGIONS}
        prev_end = {
            r: prev_addr[r] + plen - 1
            for r, plen in prev_len.items()
        }
        # compare
        for r, a in prev_end.items():
            if r in curr_addr:
                if a >= curr_addr[r]:
                    self.add_error(f"code entries overlap\n{prev}")
                # some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_desc(self, desc: str) -> None:
        self.entry_loc.field_name = K_DESC
        if not isinstance(desc, str):
            self.add_error("desc must be a string")
            return
        if not is_ascii(desc):
            self.add_error("desc must be ascii")

    def check_label(self, label: str) -> None:
        self.entry_loc.field_name = K_LABEL
        if not isinstance(label, str):
            self.add_error("label must be a string")
            return
        if not LABEL_PAT.match(label):
            self.add_error("label must be alphanumeric")

    def check_region_int(self, entry: RegionInt, align=None) -> None:
        nums = None
        if not isinstance(entry, (int, dict)):
            self.add_error("Expected integer or dictionary")
            return
        if isinstance(entry, int):
            nums = [entry]
        else:
            for k, v in entry.items():
                if k not in REGIONS:
                    self.add_error("Invalid region")
                if not isinstance(v, int):
                    self.add_error("Value must be an integer")
                    return
            nums = list(entry.values())
        if align is not None:
            for num in nums:
                if num % align != 0:
                    self.add_error(f"Number must be {align} byte aligned")

    def check_decl(self, decl: str) -> None:
        if decl is None:
            return
        self.entry_loc.field_name = K_TYPE
        tokens = tokenize_decl(decl)
        index = parse_decl(tokens, 0)
        if index != len(tokens):
            self.add_error("Invalid type")

    def check_vals(self, vals: List[EnumValEntry]) -> None:
        self.entry_loc.field_name = K_VALS
        if not isinstance(vals, list):
            self.add_error("vals must be a list")
            return
        prev = -1
        for ve in vals:
            self.check_label(ve.label)
            self.check_notes(ve.notes)
            # check val
            if not isinstance(ve.val, int):
                self.add_error("val must be an integer")
                continue
            if prev >= ve.val:
                self.add_error("vals should be in ascending order")
            prev = ve.val

    def check_vars(self, vars: List[StructVarEntry]):
        self.entry_loc.field_name = K_VARS
        if not isinstance(vars, list):
            self.add_error("vars must be a list")
            return
        prev = -1
        for ve in vars:
            self.check_label(ve.label)
            self.check_decl(ve.declaration)
            self.check_tags(ve.tags)
            self.check_enum(ve.enum)
            self.check_notes(ve.notes)
            # check offset
            self.check_region_int(ve.offset)
            if prev >= ve.offset:
                self.add_error("offsets should be in ascending order")
            prev = ve.offset

    def check_mode(self, mode: CodeMode):
        self.entry_loc.field_name = K_MODE
        if not isinstance(mode, CodeMode):
            self.add_error("Invalid mode")

    def check_params(self, params: List[VarEntry]):
        self.entry_loc.field_name = K_PARAMS
        if params is not None and not isinstance(params, list):
            self.add_error("params must be null or list")
        if isinstance(params, list):
            for param in params:
                self.check_label(param.label)
                self.check_decl(param.declaration)
                self.check_enum(param.enum)

    def check_return(self, ret: VarEntry):
        self.entry_loc.field_name = K_RETURN
        if ret is not None and not isinstance(ret, VarEntry):
            self.add_error("return must be null or dict")
        if isinstance(ret, dict):
            self.check_label(ret.label)
            self.check_decl(ret.declaration)
            self.check_enum(ret.enum)

    def check_tags(self, tags: List[DataTag]):
        if tags is None:
            return
        self.entry_loc.field_name = K_TAGS
        if not isinstance(tags, list):
            self.add_error("tags must be a list")
            return
        for tag in tags:
            if not isinstance(tag, DataTag):
                self.add_error(f"Invalid tag {tag}")

    def check_enum(self, enm: str):
        if enm is None:
            return
        self.entry_loc.field_name = K_ENUM
        if enm not in self.enums:
            self.add_error("Invalid enum")

    def check_notes(self, notes: str) -> None:
        if notes is None:
            return
        self.entry_loc.field_name = K_NOTES
        if not is_ascii(notes):
            self.add_error("notes must be ascii")


def is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


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
    yaml_files = []
    for game in GAMES:
        game_dir = os.path.join(YAML_PATH, game)
        # find all yaml files
        for root, _, files in os.walk(game_dir):
            for f in files:
                name, ext = os.path.splitext(f)
                if ext == YAML_EXT:
                    if name not in MAP_TYPES:
                        name = os.path.basename(root)
                    assert name in MAP_TYPES
                    path = os.path.join(root, f)
                    yaml_files.append((path, name))
    # parse files and output
    for path, map_type in yaml_files:
        data = load_yaml(path, map_type)
        # TODO: fix
        #write_yaml(path, data, map_type)
    print("Output YAML files")


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # convert each to json
        for map_type in MAP_TYPES:
            data = load_yamls(game, map_type)
            # TODO: convert int format if necessary
            p = os.path.join(json_dir, map_type + JSON_EXT)
            with open(p, "w") as f:
                json.dump(data, f)
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
