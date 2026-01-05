import argparse

from constants import *
from info.asset_type import TypeSpecKind
from info.game_info import GameInfo


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Dump AST")
    parser.add_argument("game", type=str)
    parser.add_argument("region", type=str)
    parser.add_argument("items", type=str, help="Comma separated symbol names")

    args = parser.parse_args()
    game = args.game.lower()
    region = args.region.upper()
    items = args.items.split(",")

    info = GameInfo(game, region)
    vars: list[str] = []
    ctx: dict[str, TypeSpecKind] = {}
    for item in items:
        de = info.get_data(item)
        vars.append(de.c_str())
        sk = de.spec_kind()
        if sk.is_tag():
            ctx[de.spec_name()] = sk

    for name, sk in ctx.items():
        if sk == TypeSpecKind.ENUM:
            print(info.enums[name].c_str())
        elif sk == TypeSpecKind.STRUCT:
            print(info.structs[name].c_str())
        elif sk == TypeSpecKind.UNION:
            print(info.unions[name].c_str())
        print()

    for v in vars:
        print(v + ";")
