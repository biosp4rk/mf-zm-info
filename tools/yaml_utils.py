import math
import os

import yaml

from constants import *
from info_entry import *
from typing import Any, List

InfoFile = List[InfoEntry]


def hex_int_presenter(dumper, data: int):
    return dumper.represent_int(f"0x{data:X}")

yaml.representer.SafeRepresenter.add_representer(int, hex_int_presenter)


def load_info_file(path: str, map_type: str) -> InfoFile:
    with open(path) as f:
        data = yaml.safe_load(f)
        assert isinstance(data, list)
        if map_type == MAP_RAM:
            return [DataEntry.from_yaml(d) for d in data]
        elif map_type == MAP_CODE:
            return [CodeEntry.from_yaml(d) for d in data]
        elif map_type == MAP_DATA:
            return [DataEntry.from_yaml(d) for d in data]
        elif map_type == MAP_STRUCTS:
            return [StructEntry.from_yaml(d) for d in data]
        elif map_type == MAP_ENUMS:
            return [EnumEntry.from_yaml(d) for d in data]
    raise ValueError()


def info_file_to_yaml(map_type: str, data: InfoFile) -> List:
    if map_type == MAP_RAM:
        return [DataEntry.to_yaml(d) for d in data]
    elif map_type == MAP_CODE:
        return [CodeEntry.to_yaml(d) for d in data]
    elif map_type == MAP_DATA:
        return [DataEntry.to_yaml(d) for d in data]
    elif map_type == MAP_STRUCTS:
        return [StructEntry.to_yaml(d) for d in data]
    elif map_type == MAP_ENUMS:
        return [EnumEntry.to_yaml(d) for d in data]
    else:
        raise ValueError()


def to_string(obj: Any) -> str:
    return yaml.safe_dump(obj, width=math.inf, sort_keys=False)


def write_info_file(path: str, map_type: str, data: InfoFile) -> None:
    yml = info_file_to_yaml(map_type, data)
    with open(path, "w") as f:
        yaml.safe_dump(yml, f, width=math.inf, sort_keys=False)


def load_info_files(
    game: str,
    map_type: str,
    region: str = None,
    include_unk: bool = False
) -> InfoFile:
    # load files and combine
    files = find_and_load_files(game, map_type, include_unk)
    data = combine_info_files(files)
    # filter by region
    if region is not None:
        data = [d for d in data if d.to_region(region)]
    data.sort()
    return data


def find_and_load_files(
    game: str,
    map_type: str,
    include_unk: bool = False
) -> List[InfoFile]:
    # find all yaml files and load data
    dir_path = os.path.join(YAML_PATH, game, map_type)
    paths = None
    if not os.path.isdir(dir_path):
        raise ValueError("No file or directory found")
    paths = [p for p in os.listdir(dir_path) if p.endswith(YAML_EXT)]
    if not include_unk:
        paths = [p for p in paths if not p.startswith("unk")]
    paths = [os.path.join(dir_path, p) for p in paths]
    return [load_info_file(p, map_type) for p in paths]


def combine_info_files(data_list: List[InfoFile]) -> InfoFile:
    combined = []
    for data in data_list:
        combined += data
    return combined
