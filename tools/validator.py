import argparse
import json
import os
import re
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
                last = {r: 0 for r in REGIONS}
                for entry in code:
                    self.entry = entry
                    self.check_desc(entry)
                    self.check_label(entry)
                    self.check_addr(entry, 4)
                    self.check_size(entry, True, 2)
                    self.check_mode(entry)
                    self.check_params(entry)
                    self.check_return(entry)
                    self.check_overlap(entry, last)

                # check data and ram
                ram_rom = [(MAP_DATA, data), (MAP_RAM, ram)]
                for map_type, entries in ram_rom:
                    self.map_type = map_type
                    last = {r: 0 for r in REGIONS}
                    for entry in entries:
                        self.entry = entry
                        self.check_desc(entry)
                        self.check_label(entry)
                        # TODO: should type be required?
                        self.check_type(entry)
                        # TODO: check if address is aligned with type
                        self.check_addr(entry)
                        self.check_count(entry)
                        size_req = "type" not in entry
                        self.check_size(entry, size_req)
                        self.check_enum(entry)
                        self.check_overlap(entry, last)
                        
        except AssertionError as e:
            print(self.game, self.map_type)
            print(self.entry)
            print(e)
            return
        print("No validation errors")

    def check_overlap(self, entry, last) -> None:
        addr = entry["addr"]
        if isinstance(addr, int):
            addr = {r: addr for r in REGIONS}
        for r, a in last.items():
            if r in addr:
                assert a < addr[r], "entries overlap"
        size = get_entry_size(entry, self.structs)
        last.update({r: addr[r] + size[r] - 1 for r in addr})

    def check_desc(self, entry) -> None:
        assert "desc" in entry, "desc is required"
        desc = entry["desc"]
        assert isinstance(desc, str), "desc must be a string"
        assert len(desc.strip()) > 0, "desc cannot be empty"

    def check_label(self, entry) -> None:
        assert "label" in entry, "label is required"
        label = entry["label"]
        assert LABEL_PAT.match(label), "label must be alphanumeric"

    def check_versioned_int(self, entry, align=None) -> None:
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
        self.check_versioned_int(addr, align)

    def check_offset(self, entry) -> None:
        assert "offset" in entry, "offset is required"
        offset = entry["offset"]
        assert isinstance(offset, int), "offset must be an integer"

    def check_count(self, entry, required: bool = False) -> None:
        if "count" not in entry:
            assert required is False, "count is required"
            return
        addr = entry["count"]
        self.check_versioned_int(addr)

    def check_size(self, entry, required: bool = False, align: int = None) -> None:
        if "size" not in entry:
            assert required is False, "size is required"
            return
        size = entry["size"]
        self.check_versioned_int(size, align)

    def check_vals(self, entry) -> None:
        assert isinstance(entry, list), "enum entry must be a list"
        prev = -0x80000001
        for val_dict in entry:
            self.check_desc(val_dict)
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
            self.check_desc(var)
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
                self.check_desc(param)
                self.check_type(param, True)
                self.check_enum(param)

    def check_return(self, entry):
        assert "return" in entry, "return is required"
        ret = entry["return"]
        assert ret is None or isinstance(
            ret, dict), "return must be null or dictionary"
        if isinstance(ret, dict):
            self.check_desc(ret)
            self.check_type(ret, True)
            self.check_enum(ret)

    def check_type(self, entry, required=False):
        if "type" not in entry:
            assert required is False, "type is required"
            return
        type_parts = entry["type"].split(".")
        for t in type_parts:
            assert t in PRIMITIVES or t in self.structs, "Invalid type"

    def check_enum(self, entry):
        if "enum" in entry:
            n = entry["enum"]
            assert n in self.enums, "Invalid enum"


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

    if args.validate:
        v = Validator()
        v.validate()
    if args.yaml:
        output_yamls()
    if args.json:
        output_jsons()
    print("Done")
