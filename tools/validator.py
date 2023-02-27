import argparse
import json
import os
import re
import sys
from typing import Dict, List

from constants import *
from game_info import GameInfo
from info_entry import *
from yaml_utils import load_yaml, load_yamls


LABEL_PAT = re.compile(r"^[A-Za-z]\w*$", flags=re.A)

TYPE_SYMS = {"*", "[", "]", "(", ")"}


class Validator(object):
    def __init__(self):
        self.game: str = None
        self.map_type: str = None
        self.entry: InfoEntry = None
        self.structs: Dict[str, StructEntry] = None
        self.enums: Dict[str, EnumEntry] = None

    def validate(self):
        try:
            for game in GAMES:
                self.game = game
                # get all info
                info = GameInfo(game)
                self.enums = info.enums
                self.structs = info.structs

                # check enums
                self.map_type = MAP_ENUMS
                for key, en in self.enums.items():
                    self.entry = key
                    assert LABEL_PAT.match(
                        key), "enum name must be alphanumeric"
                    self.check_vals(en)

                # check structs
                self.map_type = MAP_STRUCTS
                for key, st in self.structs.items():
                    self.entry = key
                    assert LABEL_PAT.match(
                        key), "struct name must be alphanumeric"
                    self.check_size(st)
                    self.check_vars(st)

                # check code
                self.map_type = MAP_CODE
                prev = None
                for entry in info.code.values():
                    self.entry = entry
                    self.check_desc(entry)
                    self.check_label(entry)
                    self.check_region_int(entry.addr, 4)
                    self.check_region_int(entry.size, 2)
                    # TODO: mode is already valid?
                    self.check_params(entry)
                    self.check_return(entry)
                    self.check_notes(entry)
                    self.check_overlap(entry, prev)
                    prev = entry

                # check data and ram
                ram_rom = [
                    (MAP_DATA, info.data.values()),
                    (MAP_RAM, info.ram.values())
                ]
                for map_type, entries in ram_rom:
                    self.map_type = map_type
                    prev = None
                    for entry in entries:
                        self.entry = entry
                        self.check_desc(entry.desc)
                        self.check_label(entry.label)
                        check_decl(entry.declaration)
                        self.check_tags(entry.tags)
                        # TODO: check if address is aligned with type
                        self.check_region_int(entry.addr)
                        self.check_enum(entry.enum)
                        self.check_notes(entry.notes)
                        self.check_overlap(entry, prev)
                        prev = entry

        except AssertionError as e:
            print(self.game, self.map_type)
            print(self.entry)
            print(e)
            return
        print("No validation errors")

    def check_overlap(self, entry, prev) -> None:
        if prev is None:
            return
        # get current address
        curr_addr = entry[K_ADDR]
        if isinstance(curr_addr, int):
            curr_addr = {r: curr_addr for r in REGIONS}
        # get end of previous
        prev_addr = prev[K_ADDR]
        if isinstance(prev_addr, int):
            prev_addr = {r: prev_addr for r in REGIONS}
        length = prev.size(self.structs)
        for r, len in length.items():
            prev_addr[r] += len - 1
        # compare
        for r, a in prev_addr.items():
            if r in curr_addr:
                assert a < curr_addr[r], f"entries overlap\n{prev}"
                # some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_desc(self, desc: str) -> None:
        assert isinstance(desc, str), "desc must be a string"
        assert is_ascii(desc), "desc must be ascii"

    def check_label(self, label: str) -> None:
        assert isinstance(label, str), "label must be a string"
        assert LABEL_PAT.match(label), "label must be alphanumeric"

    def check_region_int(self, entry: RegionInt, align=None) -> None:
        nums = None
        assert isinstance(entry, (int, dict)), "Expected integer or dictionary"
        if isinstance(entry, int):
            nums = [entry]
        else:
            for k, v in entry.items():
                assert k in REGIONS, "Invalid region"
                assert isinstance(v, int), "Value must be an integer"
            nums = list(entry.values())
        if align is not None:
            for num in nums:
                assert num % align == 0, f"Number must be {align} byte aligned"

    def check_vals(self, vals: List[EnumValEntry]) -> None:
        assert isinstance(vals, list), "vals must be a list"
        prev = -1
        for ve in vals:
            self.check_label(ve.label)
            self.check_notes(ve.notes)
            # check val
            assert isinstance(ve.val, int), "val must be an integer"
            assert prev < ve.val, "vals should be in ascending order"
            prev = ve.val

    def check_vars(self, vars: List[StructVarEntry]):
        assert isinstance(vars, list), "vars must be a list"
        prev = -1
        for ve in vars:
            self.check_label(ve.label)
            check_decl(ve.declaration)
            self.check_tags(ve.tags)
            self.check_enum(ve.enum)
            self.check_notes(ve.notes)
            # check offset
            self.check_region_int(ve.offset)
            assert prev < ve.offset, "offsets should be in ascending order"
            prev = ve.offset

    def check_params(self, params: List[VarEntry]):
        assert params is None or isinstance(
            params, list), "params must be null or list"
        if isinstance(params, list):
            for param in params:
                self.check_label(param.label)
                check_decl(param.declaration)
                self.check_enum(param.enum)

    def check_return(self, ret: VarEntry):
        assert ret is None or isinstance(
            ret, dict), "return must be null or dict"
        if isinstance(ret, dict):
            self.check_label(ret.label)
            check_decl(ret.declaration)
            self.check_enum(ret.enum)

    def check_tags(self, tags: List[DataTag]):
        assert isinstance(tags, list), "tags must be a list"
        for tag in tags:
            assert isinstance(tag, DataTag), f"Invalid tag {tag}"

    def check_enum(self, enm: str):
        assert enm in self.enums, "Invalid enum"

    def check_notes(self, notes: str) -> None:
        assert is_ascii(notes), "notes must be ascii"


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


def check_decl(decl: str) -> None:
    tokens = tokenize_decl(decl)
    index = parse_decl(tokens, 0)
    assert index == len(tokens), "Invalid type"


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
