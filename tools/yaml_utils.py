import os

import yaml

from constants import *
from info_entry import *
from typing import Dict, List, Union

InfoFile = Union[Dict[str, InfoEntry], List[InfoEntry]]


def load_yaml(path: str, map_type: str) -> InfoFile:
    with open(path) as f:
        data = yaml.safe_load(f)
        if map_type == MAP_RAM:
            return [DataEntry.from_yaml(d) for d in data]
        elif map_type == MAP_CODE:
            return [CodeEntry.from_yaml(d) for d in data]
        elif map_type == MAP_DATA:
            return [DataEntry.from_yaml(d) for d in data]
        elif map_type == MAP_STRUCTS:
            return {k: StructEntry.from_yaml(v) for k, v in data.items()}
        elif map_type == MAP_ENUMS:
            return {k: EnumEntry.from_yaml(v) for k, v in data.items()}
    raise ValueError()


def load_yamls(game: str, map_type: str, region: str = None) -> InfoFile:
    # load files and combine
    data = find_and_load_files(game, map_type)
    data = combine_yamls(data)
    # filter by region
    if region is not None and isinstance(data, list):
        data = [d for d in data if d.to_region(region)]
    return data


def find_and_load_files(game: str, map_type: str) -> List[InfoFile]:
    # find all yaml files and load data
    dir_path = os.path.join(YAML_PATH, game, map_type)
    file_path = dir_path + YAML_EXT
    paths = None
    if os.path.isfile(file_path):
        paths = [file_path]
    elif os.path.isdir(dir_path):
        paths = [p for p in os.listdir(dir_path) if p.endswith(YAML_EXT)]
        paths = [os.path.join(dir_path, p) for p in paths]
    else:
        raise ValueError("No file or directory found")
    return [load_yaml(p, map_type) for p in paths]


def combine_yamls(data_list: List[InfoFile]) -> InfoFile:
    combined = data_list[0]
    if isinstance(combined, list):
        for data in data_list[1:]:
            if isinstance(data, list):
                combined += data
            else:
                raise ValueError("Type mismatch")
        combined.sort()
    elif isinstance(combined, dict):
        for data in data_list[1:]:
            if isinstance(data, dict):
                combined.update(data)
            else:
                raise ValueError("Type mismatch")
    return combined
