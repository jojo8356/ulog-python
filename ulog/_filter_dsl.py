"""Filter DSL parser + 2 compilers — Story 4.4.

Grammar (EBNF):

    filter      ::= or_expr
    or_expr     ::= and_expr ( "OR" and_expr )*
    and_expr    ::= term ( "AND" term )*
    term        ::= "(" filter ")" | comparison
    comparison  ::= identifier op value
    op          ::= "=" | "!=" | ">" | ">=" | "<" | "<=" | "~"
    identifier  ::= LETTER ( LETTER | DIGIT | "_" | "." )*
    value       ::= STRING | NUMBER | IDENT | REL_DATE
    REL_DATE    ::= "-" NUMBER ( "s" | "min" | "h" | "d" )

NEVER calls eval()/exec(). SQL compilation produces parameterised
bind-vars only (Decision C5, NFR-SEC-50). Precedence: AND > OR
(Gap G7). Parentheses override.

Public API: `parse()`, `FilterExpr`, `FilterParseError`. AST nodes
(`And`, `Or`, `Cmp`) are exposed for inspection but the regular
caller path is `parse(dsl).to_sql()` / `parse(dsl).to_predicate()`.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

# ---- Token kinds + lexer -------------------------------------------------


class FilterParseError(Exception):
    """Raised when the DSL string cannot be parsed."""


_TOKEN_SPEC = [
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("OP_REGEX", r"~"),
    ("OP_GE", r">="),
    ("OP_LE", r"<="),
    ("OP_NE", r"!="),
    ("OP_GT", r">"),
    ("OP_LT", r"<"),
    ("OP_EQ", r"="),
    ("REL_DATE", r"-\d+(?:s|min|h|d)\b"),
    ("NUMBER", r"-?\d+(?:\.\d+)?"),
    ("STRING_D", r'"(?:[^"\\]|\\.)*"'),
    ("STRING_S", r"'(?:[^'\\]|\\.)*'"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_.]*"),
    ("WS", r"\s+"),
]

_TOKEN_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _TOKEN_SPEC))

_KEYWORDS = {"AND", "OR"}


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    col: int


def _tokenize(dsl: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(dsl):
        m = _TOKEN_RE.match(dsl, pos)
        if not m:
            raise FilterParseError(f"unexpected character at column {pos}: {dsl[pos]!r}")
        kind = m.lastgroup
        assert kind is not None
        value = m.group()
        if kind == "WS":
            pos = m.end()
            continue
        if kind == "IDENT" and value.upper() in _KEYWORDS:
            tokens.append(Token(value.upper(), value, pos))
        else:
            tokens.append(Token(kind, value, pos))
        pos = m.end()
    return tokens


# ---- AST -----------------------------------------------------------------


@dataclass(frozen=True)
class Cmp:
    key: str
    op: str  # one of: =, !=, >, >=, <, <=, ~
    value: Any  # int, float, str, datetime


@dataclass(frozen=True)
class And:
    left: FilterNode
    right: FilterNode


@dataclass(frozen=True)
class Or:
    left: FilterNode
    right: FilterNode


FilterNode = Cmp | And | Or


# ---- Parser (recursive descent) ------------------------------------------


class _Parser:
    def __init__(self, tokens: list[Token], src: str) -> None:
        self._tokens = tokens
        self._pos = 0
        self._src = src

    def _peek(self) -> Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _eat(self, *kinds: str) -> Token:
        tok = self._peek()
        if tok is None:
            raise FilterParseError(f"unexpected end of input; expected {kinds!r}")
        if tok.kind not in kinds:
            raise FilterParseError(
                f"expected {kinds!r} at column {tok.col}; got {tok.kind!r} ({tok.value!r})"
            )
        self._pos += 1
        return tok

    def parse(self) -> FilterNode:
        if not self._tokens:
            raise FilterParseError("empty filter expression")
        node = self._parse_or()
        if self._pos < len(self._tokens):
            extra = self._tokens[self._pos]
            raise FilterParseError(f"unexpected token {extra.value!r} at column {extra.col}")
        return node

    def _parse_or(self) -> FilterNode:
        node = self._parse_and()
        while True:
            tok = self._peek()
            if tok is None or tok.kind != "OR":
                break
            self._eat("OR")
            right = self._parse_and()
            node = Or(node, right)
        return node

    def _parse_and(self) -> FilterNode:
        node = self._parse_term()
        while True:
            tok = self._peek()
            if tok is None or tok.kind != "AND":
                break
            self._eat("AND")
            right = self._parse_term()
            node = And(node, right)
        return node

    def _parse_term(self) -> FilterNode:
        tok = self._peek()
        if tok is None:
            raise FilterParseError("unexpected end of input inside expression")
        if tok.kind == "LPAREN":
            self._eat("LPAREN")
            inner = self._parse_or()
            self._eat("RPAREN")
            return inner
        return self._parse_comparison()

    def _parse_comparison(self) -> Cmp:
        key_tok = self._eat("IDENT")
        op_tok = self._eat(
            "OP_EQ",
            "OP_NE",
            "OP_GT",
            "OP_GE",
            "OP_LT",
            "OP_LE",
            "OP_REGEX",
        )
        op = {
            "OP_EQ": "=",
            "OP_NE": "!=",
            "OP_GT": ">",
            "OP_GE": ">=",
            "OP_LT": "<",
            "OP_LE": "<=",
            "OP_REGEX": "~",
        }[op_tok.kind]
        value = self._parse_value()
        return Cmp(key_tok.value, op, value)

    def _parse_value(self) -> Any:
        tok = self._peek()
        if tok is None:
            raise FilterParseError("expected value after operator")
        self._pos += 1
        if tok.kind == "STRING_D":
            return _unescape(tok.value[1:-1], '"')
        if tok.kind == "STRING_S":
            return _unescape(tok.value[1:-1], "'")
        if tok.kind == "NUMBER":
            return float(tok.value) if "." in tok.value else int(tok.value)
        if tok.kind == "REL_DATE":
            return _parse_rel_date(tok.value)
        if tok.kind == "IDENT":
            return tok.value
        raise FilterParseError(
            f"expected value at column {tok.col}; got {tok.kind!r} ({tok.value!r})"
        )


def _unescape(s: str, quote: str) -> str:
    return s.replace(f"\\{quote}", quote).replace("\\\\", "\\")


_REL_RE = re.compile(r"-(\d+)(s|min|h|d)")
_REL_UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}


def _parse_rel_date(literal: str) -> datetime.datetime:
    m = _REL_RE.fullmatch(literal)
    if not m:
        raise FilterParseError(f"bad relative date: {literal!r}")
    seconds = int(m.group(1)) * _REL_UNIT_SECONDS[m.group(2)]
    return datetime.datetime.now() - datetime.timedelta(seconds=seconds)


# ---- FilterExpr wrapper + compilers --------------------------------------


@dataclass(frozen=True)
class FilterExpr:
    """Parsed AST + compilation methods (SQL + Python predicate)."""

    root: FilterNode

    def to_sql(self) -> tuple[str, dict[str, Any]]:
        """Return (where_clause, params). Bind params named :p0, :p1, …"""
        params: dict[str, Any] = {}
        clause = _to_sql(self.root, params, [0])
        return clause, params

    def to_predicate(self) -> Callable[[Mapping[str, Any]], bool]:
        """Return a callable over a record dict."""
        return _to_predicate(self.root)


# Type alias used by the inner compilers — FilterExpr.root is a FilterNode.
# `FilterExpr` itself is the user-facing wrapper.


def _to_sql(node: FilterNode, params: dict[str, Any], counter: list[int]) -> str:
    if isinstance(node, Cmp):
        pname = f"p{counter[0]}"
        counter[0] += 1
        params[pname] = node.value
        sql_op = "REGEXP" if node.op == "~" else node.op
        return f"{node.key} {sql_op} :{pname}"
    if isinstance(node, And):
        return f"({_to_sql(node.left, params, counter)} AND {_to_sql(node.right, params, counter)})"
    if isinstance(node, Or):
        return f"({_to_sql(node.left, params, counter)} OR {_to_sql(node.right, params, counter)})"
    raise TypeError(f"unknown AST node: {type(node).__name__}")


def _resolve_key(record: Mapping[str, Any], key: str) -> Any:
    """Resolve dotted keys: `context.tenant_id` → record['context']['tenant_id']."""
    cur: Any = record
    for part in key.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _to_predicate(node: FilterNode) -> Callable[[Mapping[str, Any]], bool]:
    if isinstance(node, Cmp):

        def pred(r: Mapping[str, Any]) -> bool:
            actual = _resolve_key(r, node.key)
            return _cmp(actual, node.op, node.value)

        return pred
    if isinstance(node, And):
        left = _to_predicate(node.left)
        right = _to_predicate(node.right)
        return lambda r: left(r) and right(r)
    if isinstance(node, Or):
        left = _to_predicate(node.left)
        right = _to_predicate(node.right)
        return lambda r: left(r) or right(r)
    raise TypeError(f"unknown AST node: {type(node).__name__}")


def _cmp(actual: Any, op: str, expected: Any) -> bool:
    if actual is None:
        return False
    if op == "=":
        return bool(_coerce(actual, expected) == expected)
    if op == "!=":
        return bool(_coerce(actual, expected) != expected)
    if op == "~":
        return bool(re.search(str(expected), str(actual)))
    # Ordered comparisons — try to coerce numeric / datetime.
    try:
        if op == ">":
            return bool(_coerce(actual, expected) > expected)
        if op == ">=":
            return bool(_coerce(actual, expected) >= expected)
        if op == "<":
            return bool(_coerce(actual, expected) < expected)
        if op == "<=":
            return bool(_coerce(actual, expected) <= expected)
    except TypeError:
        return False
    raise ValueError(f"unknown op {op}")


def _coerce(actual: Any, expected: Any) -> Any:
    """Type-coerce `actual` to match `expected`'s class when possible."""
    if isinstance(expected, str) and not isinstance(actual, str):
        return str(actual)
    if isinstance(expected, int) and isinstance(actual, str):
        try:
            return int(actual)
        except ValueError:
            return actual
    return actual


# ---- Public entry point --------------------------------------------------


def parse(dsl: str) -> FilterExpr:
    """Parse a DSL string into a FilterExpr (AST + compilers)."""
    if not dsl or not dsl.strip():
        raise FilterParseError("empty filter expression")
    tokens = _tokenize(dsl)
    parser = _Parser(tokens, dsl)
    return FilterExpr(parser.parse())
