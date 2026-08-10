import argparse
import json
import os
import sys

from jsonschema import Draft7Validator
from referencing import Registry, Resource

from constants import *
import info.info_file_utils as ifu


SCHEMA_PATH = "../schema"


def validate_files() -> None:
    print("Validating files...")
    # Load schema with shared definitions
    with open(os.path.join(SCHEMA_PATH, "definitions.json")) as f:
        defs_schema = json.load(f)
    defs_resource = Resource.from_contents(defs_schema)
    registry = Registry().with_resource("urn:definitions", defs_resource)

    # Go through yaml files of each type
    for map_type in MAP_TYPES:
        name = MAP_DATA if map_type == MAP_RAM else map_type
        with open(os.path.join(SCHEMA_PATH, name + JSON_EXT)) as f:
            map_schema = json.load(f)
        validator = Draft7Validator(map_schema, registry=registry)

        for game in GAMES:
            paths = ifu.find_yaml_files(game, map_type, True)
            ylists = ifu.load_yaml_files(paths)
            for path, ylist in zip(paths, ylists):
                name = os.path.basename(path)
                print(f"Checking {game} {map_type} {name}...")
                validator.validate(ylist)


def output_yamls() -> None:
    # Find all yaml files
    yaml_files = []
    for game in GAMES:
        for map_type in MAP_TYPES:
            paths = ifu.find_yaml_files(game, map_type, True)
            yaml_files += [(p, map_type) for p in paths]
    # Parse files and output
    for path, map_type in yaml_files:
        data = ifu.load_yaml_file(path)
        ifile = ifu.parse_obj_list(data, map_type)
        ifile.sort()
        ifu.write_info_file(path, map_type, ifile)
    print("Output YAML files")


def output_jsons() -> None:
    for game in GAMES:
        json_dir = os.path.join(JSON_PATH, game)
        # Convert each to json
        for map_type in MAP_TYPES:
            data = ifu.get_info_file_from_yaml(game, map_type)
            obj = ifu.info_file_to_obj(map_type, data)
            p = os.path.join(json_dir, map_type + JSON_EXT)
            with open(p, "w") as f:
                json.dump(obj, f, ensure_ascii=False)
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
        validate_files()
    if args.yaml:
        output_yamls()
    if args.json:
        output_jsons()
    print("Done")
