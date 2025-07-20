import argparse
import re

from constants import *
from info.game_info import GameInfo
from info.info_entry import NamedEntry, InfoEntry

from spellchecker import SpellChecker


UNK_NAME = re.compile(r"unk_?\w+", re.I)
HEX = re.compile(r"[0-9A-Fa-f]+")
WORD = re.compile(r"[0-9A-Za-z'\-]+")


class NameChecker:

    def __init__(self):
        self.valid_words: set[str] = None
        self.checker: SpellChecker = None
        self.misspellings: set[str] = None
    
    def check(self, game: str):
        # Setup
        info = GameInfo(game)
        self._get_valid_words(info)
        self.checker = SpellChecker()
        self.misspellings: set[str] = set()
        # Check entries
        bad = self._check_entries(info.ram, "g")
        self._print_entries(bad, "RAM")
        bad = self._check_entries(info.data, "s")
        self._print_entries(bad, "Data")
        bad = self._check_entries(info.code)
        self._print_entries(bad, "Code")
        bad = self._check_entries(info.typedefs.values())
        self._print_entries(bad, "Typedef")
        bad = self._check_entries(info.structs.values())
        self._print_entries(bad, "Struct")
        bad = self._check_entries(info.unions.values())
        self._print_entries(bad, "Union")
        bad = self._check_entries(info.enums.values())
        self._print_entries(bad, "Enum")

        # Check sub-entries
        for entry in info.structs.values():
            bad = self._check_entries(entry.vars)
            self._print_sub_entries(bad, entry)
        for entry in info.unions.values():
            bad = self._check_entries(entry.vars)
            self._print_sub_entries(bad, entry)
        for entry in info.enums.values():
            bad = self._check_entries(entry.vals)
            self._print_sub_entries(bad, entry)
        for entry in info.code:
            if entry.params:
                bad = self._check_entries(entry.params)
                self._print_sub_entries(bad, entry)

        # Check descriptions
        bad = self._check_descs(info.ram)
        self._print_entries_desc(bad, "RAM desc")
        bad = self._check_descs(info.data)
        self._print_entries_desc(bad, "Data desc")
        bad = self._check_descs(info.code)
        self._print_entries_desc(bad, "Code desc")
        bad = self._check_descs(info.typedefs.values())
        self._print_entries_desc(bad, "Typedef desc")
        bad = self._check_descs(info.structs.values())
        self._print_entries_desc(bad, "Struct desc")
        bad = self._check_descs(info.unions.values())
        self._print_entries_desc(bad, "Union desc")
        bad = self._check_descs(info.enums.values())
        self._print_entries_desc(bad, "Enum desc")
        for entry in info.code:
            bad_descs: list[str] = []
            if entry.params:
                bad = self._check_descs(entry.params)
                bad_descs += [b.desc for b in bad]
            if entry.ret and entry.ret.desc and self._check_desc(entry.ret.desc):
                bad_descs.append(entry.ret.desc)
            if bad_descs:
                print(f"{entry.name:}")
                for d in bad_descs:
                    print("    " + d)

        # Output misspellings
        if self.misspellings:
            print("\nMisspellings:")
            for word in sorted(self.misspellings):
                print(word)

    def _get_valid_words(self, info: GameInfo) -> None:
        self.valid_words = set()
        # Get words from file
        with open("info/valid_words.txt") as f:
            for line in f:
                i = line.find("#")
                word = line[:i].rstrip()
                if word:
                    self.valid_words.add(word)
        # Add names from info
        entry_lists: list[list[NamedEntry]] = [
            info.ram, info.data, info.code, info.structs.values(),
            info.unions.values(), info.enums.values()
        ]
        for entry_list in entry_lists:
            for entry in entry_list:
                self.valid_words.add(entry.name.lower())

    def _check_entries(self,
        entries: list[NamedEntry],
        prefix: str = None
    ) -> list[NamedEntry]:
        bad_entries: list[NamedEntry] = []
        for entry in entries:
            name = entry.name
            # Remove prefix
            if prefix and name.startswith(prefix):
                name = name[1:]
            # Check for unk_<hex>
            if UNK_NAME.match(name):
                continue
            # Tokenize
            words: list[str] = []
            word: list[str] = []
            i = 0
            while i < len(name):
                c = name[i]
                if c == "_":
                    if len(word) > 0:
                        words.append("".join(word))
                        word = []
                    # Skip hex following an underscore
                    m = HEX.match(name, i + 1)
                    if m:
                        i = m.endpos
                        continue
                elif c.isdigit():
                    m = HEX.match(name, i)
                    i = m.endpos
                    continue
                elif len(word) == 0 or c.islower():
                    word.append(c)
                else: # upper
                    if len(word) > 0:
                        words.append("".join(word))
                        word = [c]
                i += 1
            if len(word) > 0:
                words.append("".join(word))
            # Check for misspellings
            words = [w for w in words if w.lower() not in self.valid_words]
            misspelled = self.checker.unknown(words)
            if misspelled:
                bad_entries.append(entry)
                self.misspellings.update(misspelled)
        return bad_entries

    def _check_desc(self, desc: str) -> bool:
        words: list[str] = WORD.findall(desc)
        # Remove hex
        words = [
            w for w in words if not (
                any(c.isdigit() for c in w) and HEX.match(w)
            )
        ]
        if not words:
            return False
        words = [w for w in words if w.lower() not in self.valid_words]
        misspelled = self.checker.unknown(words)
        if misspelled:
            self.misspellings.update(misspelled)
            return True
        return False

    def _check_descs(self, entries: list[InfoEntry]) -> list[InfoEntry]:
        bad_entries: list[InfoEntry] = []
        for entry in entries:
            if not entry.desc:
                continue
            if self._check_desc(entry.desc):
                bad_entries.append(entry)
        return bad_entries

    def _print_entries(self, entries: list[NamedEntry], title: str) -> None:
        if entries:
            print(f"{title} entries:")
            for entry in entries:
                print(f"{entry.name}\t{entry.loc}")
            print()
    
    def _print_sub_entries(self, sub_entries: list[NamedEntry], entry: NamedEntry) -> None:
        if sub_entries:
            print(f"{entry.name} entries:")
            print(entry.loc)
            for entry in sub_entries:
                print(f"{entry.name}")
            print()
    
    def _print_entries_desc(self, entries: list[NamedEntry], title: str) -> None:
        if entries:
            print(f"{title} entries:")
            for entry in entries:
                print(f"{entry.name}\t{entry.loc}")
                print("    " + entry.desc)
            print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("game", type=str, choices=GAMES)

    args = parser.parse_args()
    checker = NameChecker()
    checker.check(args.game)
