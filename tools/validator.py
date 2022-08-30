import argparse
import json
import os
import re
import sys
from constants import *
from utils import get_entry_size, ints_to_strs, read_yaml, read_yamls, write_yaml


LABEL_PAT = re.compile(r"^\w+$")


class Validator(object):
    def __init__(self):
        self.game = None
        self.map_type = None
        self.entry = None
        self.enums = None
        self.structs = None

    def validate(self):
        try:
            for game in GAMES:
                self.game = game
                # get all info
                infos = [read_yamls(game, map_type) for map_type in MAP_TYPES]
                code, data, enums, ram, structs = infos
                self.enums = enums
                self.structs = structs

                # check enums
                self.map_type = MAP_ENUMS
                for key, vals in enums.items():
                    self.entry = key
                    assert LABEL_PAT.match(
                        key), "enum name must be alphanumeric"
                    self.check_vals(vals)

                # check structs
                self.map_type = "structs"
                for key, st in structs.items():
                    self.entry = key
                    assert LABEL_PAT.match(
                        key), "struct name must be alphanumeric"
                    self.check_size(st, True)
                    self.check_vars(st)

                # check code
                self.map_type = MAP_CODE
                prev = None
                for entry in code:
                    self.entry = entry
                    self.check_label(entry)
                    self.check_addr(entry, 4)
                    self.check_size(entry, True, 2)
                    self.check_mode(entry)
                    self.check_params(entry)
                    self.check_return(entry)
                    self.check_overlap(entry, prev)
                    prev = entry

                # check data and ram
                ram_rom = [(MAP_DATA, data), (MAP_RAM, ram)]
                for map_type, entries in ram_rom:
                    self.map_type = map_type
                    prev = None
                    for entry in entries:
                        self.entry = entry
                        self.check_label(entry)
                        self.check_type(entry)
                        # TODO: check if address is aligned with type
                        self.check_addr(entry)
                        self.check_count(entry)
                        size_req = "type" not in entry
                        self.check_size(entry, size_req)
                        self.check_enum(entry)
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
        curr_addr = entry["addr"]
        if isinstance(curr_addr, int):
            curr_addr = {r: curr_addr for r in REGIONS}
        # get end of previous
        prev_addr = prev["addr"]
        if isinstance(prev_addr, int):
            prev_addr = {r: prev_addr for r in REGIONS}
        size = get_entry_size(prev, self.structs)
        for r, s in size.items():
            prev_addr[r] += s - 1
        # compare
        for r, a in prev_addr.items():
            if r in curr_addr:
                assert a < curr_addr[r], f"entries overlap\n{prev}"
                # some data is in a different order in different regions,
                # so we only check against one region
                break

    def check_label(self, entry) -> None:
        assert "label" in entry, "label is required"
        label = entry["label"]
        assert LABEL_PAT.match(label), "label must be alphanumeric"

    def check_notes(self, entry) -> None:
        if "notes" not in entry:
            return
        notes = entry["notes"]
        assert isinstance(notes, str), "notes must be a string"
        assert len(notes.strip()) > 0, "notes cannot be empty"

    def check_region_int(self, entry, align=None) -> None:
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

    def check_addr(self, entry, align: int = None) -> None:
        assert "addr" in entry, "addr is required"
        addr = entry["addr"]
        self.check_region_int(addr, align)

    def check_offset(self, entry) -> None:
        assert "offset" in entry, "offset is required"
        offset = entry["offset"]
        assert isinstance(offset, int), "offset must be an integer"

    def check_count(self, entry, required: bool = False) -> None:
        if "count" not in entry:
            assert required is False, "count is required"
            return
        addr = entry["count"]
        self.check_region_int(addr)

    def check_size(self, entry, required: bool = False, align: int = None) -> None:
        if "size" not in entry:
            assert required is False, "size is required"
            return
        size = entry["size"]
        self.check_region_int(size, align)

    def check_vals(self, entry) -> None:
        assert isinstance(entry, list), "enum entry must be a list"
        prev = -0x80000001
        for val_dict in entry:
            self.check_label(val_dict)
            # check val
            assert "val" in val_dict, "val is required"
            val = val_dict["val"]
            assert isinstance(val, int), "val must be an integer"
            assert prev < val, "vals should be in ascending order"
            prev = val

    def check_vars(self, entry):
        assert "vars" in entry, "vars is required"
        vars = entry["vars"]
        assert isinstance(vars, list), "vars must be a list"
        prev = -1
        for var in vars:
            self.check_label(var)
            self.check_type(var)
            self.check_offset(var)
            self.check_count(var)
            size_req = "type" not in var
            self.check_size(var, size_req)
            self.check_enum(var)
            # check offset
            offset = var["offset"]
            assert prev < offset, "offsets should be in ascending order"
            prev = offset

    def check_mode(self, entry) -> None:
        assert "mode" in entry, "mode is required"
        mode = entry["mode"]
        assert mode in ASM_MODES, "Invalid mode"

    def check_params(self, entry):
        assert "params" in entry, "params is required"
        params = entry["params"]
        assert params is None or isinstance(
            params, list), "params must be null or list"
        if isinstance(params, list):
            for param in params:
                self.check_label(param)
                self.check_type(param)
                self.check_enum(param)

    def check_return(self, entry):
        assert "return" in entry, "return is required"
        ret = entry["return"]
        assert ret is None or isinstance(
            ret, dict), "return must be null or dictionary"
        if isinstance(ret, dict):
            self.check_label(ret)
            self.check_type(ret)
            self.check_enum(ret)

    def check_type(self, entry):
        assert "type" in entry, "type is required"
        # parse type
        t = entry["type"]
        parts = t.split()
        assert 1 <= len(parts) <= 2, f"Invalid type {t}"
        # check specifier
        spec = parts[0]
        assert (spec in PRIMITIVES or
            spec in self.structs), f"Invalid type specifier {spec}"
        if len(parts) == 2:
            check_decl(parts[1])

    def check_enum(self, entry):
        if "enum" in entry:
            n = entry["enum"]
            assert n in self.enums, "Invalid enum"


def tokenize_decl(decl: str):
    symbols = {"*", "[", "]", "(", ")"}
    tokens = []
    i = 0
    while i < len(decl):
        c = decl[i]
        if c in symbols:
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
    print(tokens)
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
        data = read_yaml(path)
        write_yaml(path, data, map_type)
    print("Output YAML files")


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # convert each to json
        for map_type in MAP_TYPES:
            data = read_yamls(game, map_type)
            ints_to_strs(data)
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
