from collections.abc import Generator, Iterable
import json
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


def find_yaml_files(
    game: str,
    map_type: str,
    include_unk: bool = False
) -> List[str]:
    """Finds all yaml files of the provided type and returns their paths."""
    dir_path = os.path.join(YAML_PATH, game, map_type)
    paths = None
    if not os.path.isdir(dir_path):
        raise ValueError("No directory found")
    paths = [p for p in os.listdir(dir_path) if p.endswith(YAML_EXT)]
    if not include_unk:
        paths = [p for p in paths if not p.startswith("unk")]
    return [os.path.join(dir_path, p) for p in paths]


def find_json_file(
    game: str,
    map_type: str
) -> List[str]:
    """Returns the path of the json file for the provided type."""
    # find all yaml files and load data
    return os.path.join(JSON_PATH, game, map_type + JSON_EXT)


def load_yaml_file(path: str) -> Any:
    """
    Loads a yaml file from the provided path
    and returns a python object.
    """
    with open(path) as f:
        return yaml.safe_load(f)


def load_yaml_files(paths: List[str]) -> Generator[Any]:
    """
    Loads each yaml file from the provided list of paths
    and returns a generator of objects.
    """
    for path in paths:
        yield load_yaml_file(path)


def load_json_file(path: str) -> Any:
    """
    Loads each yaml file from the provided list of paths
    and returns a generator of objects.
    """
    with open(path) as f:
        return json.load(f)


def parse_obj_list(ylist: Any, map_type: str) -> InfoFile:
    """
    Parses the provided object list based on the provided
    map type and returns a list of InfoEntry.
    """
    assert isinstance(ylist, list)
    if map_type == MAP_RAM:
        return [DataEntry.from_obj(d) for d in ylist]
    elif map_type == MAP_CODE:
        return [CodeEntry.from_obj(d) for d in ylist]
    elif map_type == MAP_DATA:
        return [DataEntry.from_obj(d) for d in ylist]
    elif map_type == MAP_STRUCTS:
        return [StructEntry.from_obj(d) for d in ylist]
    elif map_type == MAP_ENUMS:
        return [EnumEntry.from_obj(d) for d in ylist]
    raise ValueError(map_type)


def parse_obj_lists(ylists: Iterable[Any], map_type: str) -> Generator[InfoFile]:
    for ylist in ylists:
        yield parse_obj_list(ylist, map_type)


def combine_info_files(data_list: List[InfoFile]) -> InfoFile:
    combined = []
    for data in data_list:
        combined += data
    return combined


def get_info_file_from_yaml(
    game: str,
    map_type: str,
    region: str = None,
    include_unk: bool = False
) -> InfoFile:
    """
    Finds, loads, and parses all yaml files of the provided type
    and returns them as a single sorted list of InfoEntry.
    """
    # load files and combine
    paths = find_yaml_files(game, map_type, include_unk)
    ylists = load_yaml_files(paths)
    ifiles = parse_obj_lists(ylists, map_type)
    ifile = combine_info_files(ifiles)
    # filter by region
    if region is not None:
        ifile = [e for e in ifile if e.to_region(region)]
    ifile.sort()
    return ifile


def get_info_file_from_json(
    game: str,
    map_type: str,
    region: str = None
) -> InfoFile:
    """
    Loads and parses the json file for the provided type
    and returns it as a sorted list of InfoEntry.
    """
    # load files and combine
    path = os.path.join(JSON_PATH, game, map_type + JSON_EXT)
    obj_list = load_json_file(path)
    ifile = parse_obj_list(obj_list, map_type)
    # filter by region
    if region is not None:
        ifile = [e for e in ifile if e.to_region(region)]
    ifile.sort()
    return ifile


def info_file_to_obj(map_type: str, data: InfoFile) -> List[Any]:
    """Converts an InfoFile to an object suitable for dumping."""
    if map_type == MAP_RAM:
        return [DataEntry.to_obj(d) for d in data]
    elif map_type == MAP_CODE:
        return [CodeEntry.to_obj(d) for d in data]
    elif map_type == MAP_DATA:
        return [DataEntry.to_obj(d) for d in data]
    elif map_type == MAP_STRUCTS:
        return [StructEntry.to_obj(d) for d in data]
    elif map_type == MAP_ENUMS:
        return [EnumEntry.to_obj(d) for d in data]
    else:
        raise ValueError()


def obj_to_yaml_str(obj: Any) -> str:
    return yaml.safe_dump(obj, width=math.inf, sort_keys=False)


def write_info_file(path: str, map_type: str, data: InfoFile) -> None:
    data = info_file_to_obj(map_type, data)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, width=math.inf, sort_keys=False)

