from typing import Callable, List


ABBREVIATIONS = {
    "Alternate": "Alt",
    "Animation": "Anim",
    "Background": "Bg",
    "Calculate": "Calc",
    "Current": "Curr",
    "Definition": "Def",
    "Graphics": "Gfx",
    "Initialize": "Init",
    "Navigation": "Nav",
    "Number": "Num",
    "Previous": "Prev",
    "Pointer": "Ptr",
    "Unknown": "Unk",
}

ALL_CAPS = {
    "bg", "bldy", "io", "oam", "ram", "sram", "x", "y"
}

CAPITALIZE = {
    "metroid", "ridley", "samus"
}

class IdentSplitter:
    def __init__(self):
        self.ident = None
        self.idx = None
        self.word = None

    def split(self, ident: str) -> List[str]:
        self.ident = ident
        self.idx = 0
        words = []
        while self.idx < len(self.ident):
            c = self.ident[self.idx]
            self.idx += 1
            self.word = [c]
            if "0" <= c <= "9":
                self.get_while(self.is_digit)
            elif "A" <= c <= "Z":
                self.get_while(self.is_lower)
            elif "a" <= c <= "z":
                self.get_while(self.is_lower)
            elif c == "_":
                self.skip_while(self.is_underscore)
            else:
                raise ValueError(f"Invalid identifier char '{c}'")
            words.append("".join(self.word))
        return words

    @staticmethod
    def is_digit(c: str) -> bool:
        return "0" <= c <= "9"

    @staticmethod
    def is_upper(c: str) -> bool:
        return "A" <= c <= "Z"

    @staticmethod
    def is_lower(c: str) -> bool:
        return "a" <= c <= "z"

    @staticmethod
    def is_underscore(c: str) -> bool:
        return c == "_"

    def get_while(self, cond: Callable[[str], bool]) -> None:
        while self.idx < len(self.ident) and cond(self.ident[self.idx]):
            self.word.append(self.ident[self.idx])
            self.idx += 1

    def skip_while(self, cond: Callable[[str], bool]) -> None:
        while self.idx < len(self.ident) and cond(self.ident[self.idx]):
            self.idx += 1


def desc_from_ident(ident: str) -> str:
    words = IdentSplitter().split(ident)
    words = [w.lower() for w in words if w != "_"]
    for i in range(len(words)):
        word = words[i]
        if word in ALL_CAPS:
            words[i] = word.upper()
        elif word in CAPITALIZE:
            words[i] = word.capitalize()
    first = words[0]
    words[0] = first[0].upper() + first[1:]
    return " ".join(words)


def label_from_ident(ident: str) -> str:
    words = IdentSplitter().split(ident)
    words = [w.capitalize() for w in words]
    words = [ABBREVIATIONS.get(w, w) for w in words]
    return "".join(words)
