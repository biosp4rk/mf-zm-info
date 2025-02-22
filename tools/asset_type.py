import argparse
from abc import ABC, abstractmethod
from enum import Enum, auto
import re


# -------- AST --------


class DataType(Enum):

    VOID = auto()
    U8 = auto()
    S8 = auto()
    U16 = auto()
    S16 = auto()
    U32 = auto()
    S32 = auto()
    ENUM = auto()
    STRUCT = auto()
    UNION = auto()

    def is_tag(self) -> bool:
        return (
            self == DataType.ENUM or
            self == DataType.STRUCT or
            self == DataType.UNION
        )


class AssetType(ABC):

    @abstractmethod
    def base_type(self) -> DataType:
        pass

    @abstractmethod
    def spec_name(self) -> str:
        pass

    @abstractmethod
    def decl_str(self, decl: str = "") -> str:
        pass


class SpecifierType(AssetType):

    def __init__(self, data_type: DataType):
        self.data_type = data_type

    def base_type(self) -> DataType:
        return self.data_type


class PrimitiveType(SpecifierType):

    def __init__(self, data_type: DataType):
        assert not data_type.is_tag()
        super().__init__(data_type)

    def spec_name(self) -> str:
        return self.data_type.name.lower()

    def decl_str(self, decl: str = "") -> str:
        if decl:
            return f"{self.spec_name()} {decl}"
        return self.spec_name()

    def __str__(self) -> str:
        return self.spec_name()


class TaggedType(SpecifierType):

    def __init__(self, data_type: DataType, name: str):
        assert data_type.is_tag()
        super().__init__(data_type)
        self.name = name

    def spec_name(self) -> str:
        return self.name

    def decl_str(self, decl: str = "") -> str:
        tag_str = f"{self.data_type.name.lower()} {self.name}"
        if decl:
            return f"{tag_str} {decl}"
        return tag_str

    def __str__(self) -> str:
        return f"{self.data_type.name.lower()} {self.name}"


class OuterType(AssetType):

    def __init__(self, inner_type: AssetType):
        self.inner_type = inner_type

    def base_type(self) -> DataType:
        return self.inner_type.base_type()

    def spec_name(self) -> str:
        return self.inner_type.spec_name()


class PointerType(OuterType):

    def __init__(self, inner_type: AssetType):
        super().__init__(inner_type)

    def decl_str(self, decl: str = "") -> str:
        ptr_str = "*" + decl
        if isinstance(self.inner_type, (ArrayType, FunctionType)):
            ptr_str = f"({ptr_str})"
        return self.inner_type.decl_str(ptr_str)

    def __str__(self) -> str:
        return f"pointer to {self.inner_type}"


class ArrayType(OuterType):

    def __init__(self, inner_type: AssetType, size: int):
        super().__init__(inner_type)
        self.size = size

    def decl_str(self, decl: str = "") -> str:
        arr_str = f"[0x{self.size:X}]"
        return self.inner_type.decl_str(decl + arr_str)

    def __str__(self) -> str:
        size_str = "" if self.size is None else f" {self.size}"
        return f"array{size_str} of {self.inner_type}"


class FunctionType(OuterType):

    def __init__(self, inner_type: AssetType, params: list[AssetType]):
        super().__init__(inner_type)
        self.params = params

    def decl_str(self, decl: str = "") -> str:
        param_str = ""
        if self.params:
            param_str = ", ".join(p.decl_str() for p in self.params)
        return self.inner_type.decl_str(decl + f"({param_str})")

    def __str__(self) -> str:
        param_str = ""
        if self.params:
            param_str = ", ".join(str(p) for p in self.params)
            param_str = f" ({param_str})"
        return f"function{param_str} returning {self.inner_type}"


# -------- Tokenizer --------


class TokenName(Enum):

    EOS = auto()
    # Identifiers and literals
    IDENT = auto()          # [A-Za-z_][A-Za-z0-9_]*
    INT = auto()            # [0-9][A-Za-z0-9_]*
    # Separators
    L_PAREN = auto()        # (
    R_PAREN = auto()        # )
    L_BRACK = auto()        # [
    R_BRACK = auto()        # ]
    STAR = auto()           # *
    COMMA = auto()          # ,
    # Specifiers and qualifiers
    TYPE_SPEC = auto()      # Ex: u8
    # TYPE_QUAL = auto()    # Ex: const
    # STORE_SPEC = auto()   # Ex: static


class Token:

    def __init__(self, name: TokenName, text: str):
        self.name = name
        self.text = text
    
    def __str__(self) -> str:
        return f"({self.name.name}, {self.text})"


SINGLE_CHAR_TOKENS = {
    "(": TokenName.L_PAREN,
    ")": TokenName.R_PAREN,
    "[": TokenName.L_BRACK,
    "]": TokenName.R_BRACK,
    "*": TokenName.STAR,
    ",": TokenName.COMMA
}

KEYWORDS = {
    # Type specifieres
    "void": TokenName.TYPE_SPEC,
    "u8": TokenName.TYPE_SPEC,
    "u16": TokenName.TYPE_SPEC,
    "u32": TokenName.TYPE_SPEC,
    "s8": TokenName.TYPE_SPEC,
    "s16": TokenName.TYPE_SPEC,
    "s32": TokenName.TYPE_SPEC,
    "enum": TokenName.TYPE_SPEC,
    "struct": TokenName.TYPE_SPEC,
    "union": TokenName.TYPE_SPEC,
    # # Type qualifiers
    # "const": TokenName.TYPE_QUAL,
    # "volatile": TokenName.TYPE_QUAL,
    # # Storage qualifiers
    # "extern": TokenName.STORAGE,
    # "static": TokenName.STORAGE,
    # "auto": TokenName.STORAGE,
    # "register": TokenName.STORAGE
}

class TypeTokenizer:

    def __init__(self):
        self.tokens: list[Token] = None
        self.index: int = None
        self.token_index: int = None
        self.text: str = None

    def tokenize(self, text: str) -> list[Token]:
        self.tokens = []
        self.index = 0
        self.text = text
        while self.index < len(text):
            self.token_index = self.index
            c = text[self.index]
            self.index += 1
            # Skip whitespace
            if c == " ":
                continue
            # Check separator
            name = SINGLE_CHAR_TOKENS.get(c)
            if name is not None:
                self._add_token(name, c)
            # Check integer
            elif re.match(r"[0-9]", c):
                self._add_token(TokenName.INT, self._alpha_num())
            # Check identifier
            elif re.match(r"[A-Za-z_]", c):
                ident = self._alpha_num()
                name = KEYWORDS.get(ident)
                if name is None:
                    name = TokenName.IDENT
                self._add_token(name, ident)
            else:
                raise ValueError(f"Unrecognized character '{c}'")
        self._add_token(TokenName.EOS, "")
        return self.tokens

    def _alpha_num(self) -> str:
        while self.index < len(self.text):
            c = self.text[self.index]
            if re.match(r"[A-Za-z0-9_]", c):
                self.index += 1
            else:
                break
        return self.text[self.token_index : self.index]

    def _add_token(self, name: TokenName, text: str) -> None:
        self.tokens.append(Token(name, text))


# -------- Parser --------


DATA_TYPE_STRS = {
    "void": DataType.VOID,
    "u8": DataType.U8,
    "u16": DataType.U16,
    "u32": DataType.U32,
    "s8": DataType.S8,
    "s16": DataType.S16,
    "s32": DataType.S32,
    "enum": DataType.ENUM,
    "struct": DataType.STRUCT,
    "union": DataType.UNION
}


class TypeParser:

    def __init__(self):
        self.tokens: list[Token] = None
        self.index: int = None
        self.curr_token: Token = None
        self.prev_token: Token = None

    def parse(self, tokens: list[Token]) -> AssetType:
        self.tokens = tokens
        self.index = -1
        self.curr_token = None
        self._next_token()
        root = self._parse_decl(0)
        if self.curr_token.name != TokenName.EOS:
            raise ValueError("Expected EOS")
        return root

    def _next_token(self) -> None:
        self.prev_token = self.curr_token
        self.index += 1
        self.curr_token = self.tokens[self.index]

    def _accept(self, name: TokenName) -> bool:
        if self.curr_token.name == name:
            self._next_token()
            return True
        return False

    def _expect(self, name: TokenName) -> None:
        if not self._accept(name):
            raise ValueError(f"Expected {name.name} but got {self.curr_token.name}")

    def _parse_decl(self, start: int) -> AssetType:
        def update_parent_types(new_type: OuterType):
            nonlocal root
            nonlocal outer
            if outer is None:
                root = new_type
            else:
                outer.inner_type = new_type
            outer = new_type
        in_param = start > 0
        # First token must be type spec
        spec = self._parse_type_spec()
        # Update left end index
        start = self.index - 1
        # Find middle of declaration
        self._find_decl_middle()
        left = self.index - 1
        # Parse from middle outwards
        root: AssetType = spec
        outer: OuterType = None
        while True:
            if self._accept(TokenName.L_BRACK):
                self._expect(TokenName.INT)
                size = int(self.prev_token.text[2:], 16)
                self._expect(TokenName.R_BRACK)
                arr_type = ArrayType(spec, size)
                update_parent_types(arr_type)
            elif self._accept(TokenName.L_PAREN):
                params: list[AssetType] = []
                if not self._accept(TokenName.R_PAREN):
                    while True:
                        param_type = self._parse_decl(self.index)
                        if self.curr_token.name == TokenName.EOS:
                            raise ValueError("Unexpected EOS while parsing function parameters")
                        params.append(param_type)
                        if self._accept(TokenName.R_PAREN):
                            break
                        self._expect(TokenName.COMMA)
                func_type = FunctionType(spec, params)
                update_parent_types(func_type)
            elif self.curr_token.name == TokenName.R_PAREN:
                while left > start:
                    name = self.tokens[left].name
                    left -= 1
                    if name == TokenName.STAR:
                        ptr_type = PointerType(spec)
                        update_parent_types(ptr_type)
                    elif name == TokenName.L_PAREN:
                        self._next_token()
                        break
                if in_param and left == start:
                    break
            elif (
                self.curr_token.name == TokenName.EOS or
                self.curr_token.name == TokenName.COMMA
            ):
                while left > start:
                    name = self.tokens[left].name
                    left -= 1
                    if name == TokenName.STAR:
                        ptr_type = PointerType(spec)
                        update_parent_types(ptr_type)
                    elif name == TokenName.L_PAREN:
                        tn = self.curr_token.name.name
                        raise ValueError(f"Unexpected token {tn}")
                break
            else:
                tn = self.curr_token.name.name
                raise ValueError(f"Unexpected token {tn}")
        return root

    def _parse_type_spec(self) -> AssetType:
        self._expect(TokenName.TYPE_SPEC)
        data_type = DATA_TYPE_STRS[self.prev_token.text]
        if data_type.is_tag():
            self._expect(TokenName.IDENT)
            return TaggedType(data_type, self.prev_token.text)
        else:
            return PrimitiveType(data_type)

    def _find_decl_middle(self) -> None:
        while True:
            if self._accept(TokenName.STAR):
                continue
            if self.curr_token.name == TokenName.L_PAREN:
                next_token = self.tokens[self.index + 1].name
                if next_token != TokenName.R_PAREN and next_token != TokenName.TYPE_SPEC:
                    self._next_token()
                    continue
            break

    # TODO: Remove
    def _print_state(self, start: int, left: int) -> None:
        items = []
        for i, t in enumerate(self.tokens):
            if i == start:
                prefix = "S="
            elif i == left:
                prefix = "L="
            elif i == self.index:
                prefix = "R="
            else:
                prefix = ""
            items.append(prefix + t.text)
        print(" ".join(items))


TEST_CASES = [
    "u8",
    "u8 *",
    "u8 [0x2]",
    "u8 ()",
    "u8 (void)",
    "u8 (u16, u32)",
    "u8 **",
    "u8 *[0x2]",
    "u8 *()",
    "u8 *(void)",
    "u8 *(u16, u32)",
    "u8 [0x2][0x4]",
    "u8 [0x2]()",
    "u8 [0x2](void)",
    "u8 [0x2](u16, u32)",
    "u8 ()()",
    "u8 ()[0x2]",
    #
    "u8 (*[0x2])[0x4]",
]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("text", type=str)

    args = parser.parse_args()

    tokenizer = TypeTokenizer()
    parser = TypeParser()

    tokens = tokenizer.tokenize(args.text)
    node = parser.parse(tokens)
    print(node)
