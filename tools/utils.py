import math
import os
import re
from typing import Any, Dict, List, Tuple, Union
import yaml
from constants import *


InfoFile = Union[Dict, List]


def hexint_presenter(dumper, data):
    return dumper.represent_int(f"0x{data:X}")


yaml.add_representer(int, hexint_presenter)


def read_yaml(path: str) -> InfoFile:
    with open(path) as f:
        return yaml.full_load(f)


def read_yamls(game: str, map_type: str, region: str = None) -> InfoFile:
    dir_path = os.path.join(YAML_PATH, game, map_type)
    file_path = dir_path + YAML_EXT
    data_dict = None
    if os.path.isfile(file_path):
        data_dict = {file_path: read_yaml(file_path)}
    elif os.path.isdir(dir_path):
        files = [f for f in os.listdir(dir_path) if f.endswith(YAML_EXT)]
        files = [os.path.join(dir_path, f) for f in files]
        data_dict = {f: read_yaml(f) for f in files}
    else:
        raise ValueError("No file or directory found")
    combined = combine_yamls(list(data_dict.values()))
    if region is not None:
        combined = filter_by_region(combined, region)
    return combined


def combine_yamls(data_list: List[InfoFile]) -> InfoFile:
    combined = data_list[0]
    for data in data_list[1:]:
        if isinstance(combined, list) and isinstance(data, list):
            combined += data
        elif isinstance(combined, dict) and isinstance(data, dict):
            combined.update(data)
        else:
            raise ValueError("Type mismatch")
    if isinstance(combined, list):
        # get entries by region
        entry_dict = {r: [] for r in REGIONS}
        for entry in combined:
            addr = entry[K_ADDR]
            if isinstance(addr, int):
                reg = REGIONS[0]
            else:
                reg = next(r for r in REGIONS if r in addr)
            entry_dict[reg].append(entry)
        # sort by U, then by E, etc
        for r in REGIONS:
            entries = sorted(entry_dict[r],
                key=lambda e: region_int_to_int(r, e[K_ADDR]))
            if r == REGIONS[0]:
                combined = entries
                continue
            i = len(entries) - 1
            j = len(combined) - 1
            while i >= 0:
                entry = entries[i]
                addr = region_int_to_int(r, entry[K_ADDR])
                while j >= 0:
                    cmp_addr = combined[j][K_ADDR]
                    if isinstance(cmp_addr, dict):
                        cmp_addr = cmp_addr.get(r, 2e32)
                    if cmp_addr < addr:
                        break
                    j -= 1
                combined.insert(j + 1, entry)
                i -= 1
    return combined


def filter_by_region(data_list: List[Dict], region: str) -> List[Dict]:
    filtered = []
    for entry in data_list:
        addr = entry["addr"]
        addr = region_int_to_int(region, addr)
        if addr is not None:
            entry["addr"] = addr
            filtered.append(entry)
    return filtered


def region_int_to_int(region: str, entry: RegionInt) -> int:
    if isinstance(entry, int):
        return entry
    return entry.get(region)


def region_int_to_dict(regions: List[str], entry: RegionInt) -> Dict[str, int]:
    if isinstance(entry, dict):
        return entry
    return {r: entry for r in regions}


def compare_addrs(entry1, entry2) -> int:
    addr1 = entry1[K_ADDR]
    addr2 = entry2[K_ADDR]
    if isinstance(addr1, dict):
        for region in REGIONS:
            if region in addr1 and region in addr2:
                addr1 = addr1[region]
                addr2 = addr2[region]
                break
        if isinstance(addr1, dict):
            return 0
    return addr1 - addr2


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


def write_yaml(path: str, data: InfoFile, map_type: str) -> None:
    # create stack of entries
    if isinstance(data, dict):
        stack = [(v, map_type) for v in data.values()]
    elif isinstance(data, list):
        stack = [(d, map_type) for d in data]
    else:
        raise ValueError("Bad format")
    # check for required fields
    while len(stack) > 0:
        entry, k = stack.pop()
        if isinstance(entry, dict):
            fields = FIELDS[k]
            for i, field in enumerate(fields):
                if field in entry:
                    v = entry.pop(field)
                    # add index to keep fields in order
                    entry[f"{i:03}~{field}"] = v
                    stack.append((v, field))
        elif isinstance(entry, list):
            stack += [(e, k) for e in entry]

    # get output
    output = yaml.dump(data, width=math.inf)
    # remove index from fields
    output = re.sub(r"\d+~", "", output)
    if isinstance(data, list):
        # add extra line breaks for lists
        output = re.sub(r"^- ", "-\n  ", output, flags=re.M)
    with open(path, "w") as f:
        f.write(output)


# gets the total physical size of all items
def get_entry_length(
    entry: Dict[str, Any], structs: Dict[str, Any]
) -> Dict[str, int]:
    size, count = get_entry_size_count(entry, structs)
    return {r: s * count for r, s in size.items()}


# gets the individual size and number of items
def get_entry_size_count(
    entry: Dict[str, Any], structs: Dict[str, Any]
) -> Dict[str, int]:
    # return size field if present
    if K_SIZE in entry:
        regions = get_entry_regions(entry)
        size = region_int_to_dict(regions, entry[K_SIZE])
        return size, 1
    # parse type to get size and count
    size = get_entry_size(entry, structs)
    parts = entry[K_TYPE].split()
    count = get_type_count(parts)
    return size, count


# gets the number of items (1 unless array type)
def get_type_count(parts: List[str]) -> int:
    count = 1
    if len(parts) == 2:
        decl = parts[1]
        # get inner most part of declaration
        i = decl.rfind("(")
        if i != -1:
            j = decl.find(")")
            decl = decl[i+1:j]
        # check for pointer
        if decl[0] == "*":
            decl = decl.lstrip("*")
        # check for array
        dims = re.findall(r"(?:0x)?[0-9A-F]+", decl)
        for dim in dims:
            radix = 16 if dim.startswith("0x") else 10
            count *= int(dim, radix)
    return count


# gets the physical size of an individual item
def get_entry_size(
    entry: Dict[str, Any], structs: Dict[str, Any]
) -> Dict[str, int]:
    regions = get_entry_regions(entry)
    # parse type
    parts = entry[K_TYPE].split()
    if is_ptr_type(parts):
        return {r: 4 for r in regions}
    spec = parts[0]
    size = get_spec_size(spec, structs)
    return {r: size for r in regions}


def get_entry_regions(entry: Dict[str, Any]) -> Tuple[str]:
    addr = entry[K_ADDR]
    if isinstance(addr, dict):
        return tuple(addr.keys())
    return REGIONS


def is_ptr_type(parts: List[str]) -> bool:
    # get second part of type string
    if len(parts) != 2:
        return False
    decl = parts[1]
    # find inner most part of declaration
    i = decl.rfind("(")
    i += 1
    # check for pointer
    return decl[i] == '*'


def get_spec_size(spec: str, structs: Dict[str, Any]) -> int:
    if spec in PRIMITIVES:
        return PRIMITIVES[spec]
    if spec in structs:
        return structs[spec][K_SIZE]
    raise ValueError(f"Invalid type specifier {spec}")
