from collections.abc import Generator, Iterable
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
    """
    Finds all yaml files of the provided type
    and returns their paths.
    """
    # find all yaml files and load data
    dir_path = os.path.join(YAML_PATH, game, map_type)
    paths = None
    if not os.path.isdir(dir_path):
        raise ValueError("No directory found")
    paths = [p for p in os.listdir(dir_path) if p.endswith(YAML_EXT)]
    if not include_unk:
        paths = [p for p in paths if not p.startswith("unk")]
    return [os.path.join(dir_path, p) for p in paths]


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


def parse_yaml_data(data: Any, map_type: str) -> InfoFile:
    """
    Parses the provided object based on the provided map type
    and returns a list of InfoEntry.
    """
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


def parse_yaml_datas(datas: Iterable[Any], map_type: str) -> Generator[InfoFile]:
    for data in datas:
        yield parse_yaml_data(data, map_type)


def combine_info_files(data_list: List[InfoFile]) -> InfoFile:
    combined = []
    for data in data_list:
        combined += data
    return combined


def get_info_files(
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
    datas = load_yaml_files(paths)
    ifiles = parse_yaml_datas(datas, map_type)
    ifile = combine_info_files(ifiles)
    # filter by region
    if region is not None:
        ifile = [e for e in ifile if e.to_region(region)]
    ifile.sort()
    return ifile


def info_file_to_yaml(map_type: str, data: InfoFile) -> List[Any]:
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


def yaml_data_to_str(obj: Any) -> str:
    return yaml.safe_dump(obj, width=math.inf, sort_keys=False)


def write_info_file(path: str, map_type: str, data: InfoFile) -> None:
    data = info_file_to_yaml(map_type, data)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, width=math.inf, sort_keys=False)

