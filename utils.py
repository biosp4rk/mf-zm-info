import argparse
import json
import os
import re
import yaml
from typing import Dict, List, Union

InfoFile = Union[Dict, List]

YAML_PATH = "yaml"
YAML_EXT = ".yml"
JSON_PATH = "json"
JSON_EXT = ".json"

GAMES = ("mf", "zm")
NAMES = ("code", "data", "enums", "ram", "structs")

DATA = (
    ("desc", True),
    ("label", False),
    ("type", False),
    ("addr", True),
    ("size", False),
    ("count", False),
    ("enum", False)
)
REGIONS = (
    ("U", False),
    ("E", False),
    ("J", False)
)
FIELDS = {
    "structs": (
        ("size", True),
        ("vars", True)
    ),
    "vars":  (
        ("desc", True),
        ("type", False),
        ("offset", True),
        ("size", False),
        ("count", False),
        ("enum", False)
    ),
    "enums": (
        ("desc", True),
        ("val", True)
    ),
    "code": (
        ("desc", True),
        ("label", False),
        ("addr", True),
        ("size", True),
        ("mode", True),
        ("params", True),
        ("return", True)
    ),
    "ram": DATA,
    "data": DATA,
    "addr": REGIONS,
    "size": REGIONS,
    "count": REGIONS
}
PRIMITIVES = {
    "u8", "s8", "flags8",
    "u16", "s16", "flags16",
    "u32", "s32", "ptr",
    "char", "lz", "gfx", "palette"
}


def hexint_presenter(dumper, data):
    return dumper.represent_int(f"0x{data:X}")
yaml.add_representer(int, hexint_presenter)


def load_yaml(path: str) -> InfoFile:
    with open(path) as f:
        return yaml.full_load(f)


def load_yamls(game: str, name: str) -> InfoFile:
    dir_path = os.path.join(YAML_PATH, game, name)
    file_path = dir_path + YAML_EXT
    data_dict = None
    if os.path.isfile(file_path):
        data_dict = {file_path: load_yaml(file_path)}
    elif os.path.isdir(dir_path):
        files = [f for f in os.listdir(dir_path) if f.endswith(YAML_EXT)]
        files = [os.path.join(dir_path, f) for f in files]
        data_dict = {f: load_yaml(f) for f in files}
    else:
        raise ValueError("No file or directory found")
    return combine_yamls(list(data_dict.values()))


def combine_yamls(data_list: List[InfoFile]) -> InfoFile:
    combined = data_list[0]
    for data in data_list[1:]:
        if isinstance(combined, list) and isinstance(data, list):
            combined += data
        elif isinstance(combined, dict) and isinstance(data, dict):
            combined.update(data)
        else:
            raise ValueError("Type mismatch")
    return combined


def check_refs() -> None:
    for game in GAMES:
        # load yaml files
        # TODO: check code too
        data = load_yamls(game, "data")
        enums = load_yamls(game, "enums")
        ram = load_yamls(game, "ram")
        structs = load_yamls(game, "structs")
        # check if enum/struct references match
        data_list = data + ram
        for s in structs.values():
            data_list += s["vars"]
        for entry in data_list:
            if "type" in entry:
                t = entry["type"].split(".")[0]
                if t not in PRIMITIVES and t not in structs:
                    desc = entry["desc"]
                    raise ValueError(
                        f"{game}: Struct {t} in entry {desc} was not found")
            if "enum" in entry:
                en = entry["enum"]
                if en not in enums:
                    desc = entry["desc"]
                    raise ValueError(
                        f"{game}: Enum {en} in entry {desc} was not found")
    print("No reference errors found")


def ints_to_strs(data: InfoFile) -> None:
    stack = [data]
    while len(stack) > 0:
        entry = stack.pop()
        if isinstance(entry, list):
            stack += entry
        elif isinstance(entry, dict):
            for k, v in entry.items():
                if isinstance(v, int):
                    entry[k] = f"{v:X}"
                elif isinstance(v, list):
                    stack += v
                else:
                    stack.append(v)


def output_yaml(path: str, data: InfoFile, name: str) -> None:
    # create stack of entries
    if isinstance(data, dict):
        stack = [(v, name) for v in data.values()]
    elif isinstance(data, list):
        stack = [(d, name) for d in data]
    else:
        raise ValueError("Bad format")
    # check for required fields
    while len(stack) > 0:
        entry, k = stack.pop()
        if isinstance(entry, dict):
            fields = FIELDS[k]
            for i, field in enumerate(fields):
                name, required = field
                if name in entry:
                    v = entry.pop(name)
                    # add index to keep fields in order
                    entry[f"{i:02}~{name}"] = v
                    stack.append((v, name))
                elif required:
                    raise ValueError(entry)
        elif isinstance(entry, list):
            stack += [(e, k) for e in entry]
    # get output
    output = yaml.dump(data)
    # remove index from fields
    output = re.sub(r"\d\d~", "", output)
    if isinstance(data, list):
        # add extra line breaks for lists
        output = re.sub(r"^- ", "-\n  ", output, flags=re.MULTILINE)
    # try parsing output to make sure it's valid
    yaml.full_load(output)
    with open(path, "w") as f:
        f.write(output)


def output_yamls() -> None:
    yaml_files = []
    for game in GAMES:
        game_dir = os.path.join(YAML_PATH, game)
        # find all yaml files
        for root, _, files in os.walk(game_dir):
            for f in files:
                name, ext = os.path.splitext(f)
                if ext == YAML_EXT:
                    if name not in NAMES:
                        name = os.path.basename(root)
                    assert name in NAMES
                    path = os.path.join(root, f)
                    yaml_files.append((path, name))
    # parse files and output
    for path, name in yaml_files:
        data = load_yaml(path)
        output_yaml(path, data, name)


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # convert each to json
        for name in NAMES:
            data = load_yamls(game, name)
            ints_to_strs(data)
            p = os.path.join(json_dir, name + JSON_EXT)
            with open(p, "w") as f:
                json.dump(data, f)
    print("Output JSON files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--refs", action="store_true")
    parser.add_argument("-y", "--yaml", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args()

    if args.refs:
        check_refs()
    if args.yaml:
        output_yamls()
    if args.json:
        output_jsons()
    print("Done")
