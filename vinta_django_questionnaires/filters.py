"""A small filter DSL that compiles to a Django ``Q`` object.

Value sets backed by a model store their filter as a string so that the people
authoring questionnaires never have to write Python::

    status = "active" and not category.slug in ["draft", "internal"]
    published_at >= "2026-01-01" or is_featured = true

The grammar is deliberately tiny:

``expression``
    ``or_expression``
``or_expression``
    ``and_expression ("or" and_expression)*``
``and_expression``
    ``unary ("and" unary)*``
``unary``
    ``"not" unary | "(" expression ")" | comparison``
``comparison``
    ``field operator value``

Fields are dotted paths -- ``category.slug`` becomes the ORM path
``category__slug``.  Operators are either the symbols ``= == != > >= < <=`` or
one of the named lookups below, optionally preceded by ``not``.  Values are
strings, numbers, ``true``/``false``/``null``, or a bracketed list of those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

#: Symbolic operators, mapped to the ORM lookup they use and whether they negate.
SYMBOL_LOOKUPS: dict[str, tuple[str, bool]] = {
    "=": ("exact", False),
    "==": ("exact", False),
    "!=": ("exact", True),
    ">": ("gt", False),
    ">=": ("gte", False),
    "<": ("lt", False),
    "<=": ("lte", False),
}

#: Lookups that may be spelled out by name, e.g. ``title icontains "foo"``.
NAMED_LOOKUPS = frozenset(
    {
        "contains",
        "endswith",
        "exact",
        "gt",
        "gte",
        "icontains",
        "iendswith",
        "iexact",
        "in",
        "iregex",
        "isnull",
        "istartswith",
        "lt",
        "lte",
        "range",
        "regex",
        "startswith",
    }
)

LITERALS: dict[str, Any] = {"true": True, "false": False, "null": None, "none": None}
KEYWORDS = frozenset({"and", "or", "not"}) | set(LITERALS) | NAMED_LOOKUPS

_TOKEN_RE = re.compile(
    r"""
      (?P<whitespace>\s+)
    | (?P<lparen>\()
    | (?P<rparen>\))
    | (?P<lbracket>\[)
    | (?P<rbracket>\])
    | (?P<comma>,)
    | (?P<operator>!=|>=|<=|==|=|>|<)
    | (?P<string>'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")
    | (?P<number>-?\d+(?:\.\d+)?)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
    """,
    re.VERBOSE,
)


class FilterExpressionError(ValueError):
    """Raised when a filter expression cannot be parsed."""

    def __init__(self, message: str, position: int | None = None) -> None:
        super().__init__(message if position is None else f"{message} (at position {position})")
        self.position = position


@dataclass(frozen=True)
class Token:
    kind: str
    value: Any
    position: int


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    while position < len(expression):
        match = _TOKEN_RE.match(expression, position)
        if match is None:
            raise FilterExpressionError(f"Unexpected character {expression[position]!r}", position)
        kind = match.lastgroup or ""
        if kind != "whitespace":
            tokens.append(Token(kind=kind, value=match.group(), position=position))
        position = match.end()
    tokens.append(Token(kind="end", value="", position=position))
    return tokens


def _parse_string(raw: str) -> str:
    body = raw[1:-1]
    return re.sub(r"\\(.)", r"\1", body)


def _parse_number(raw: str) -> int | float:
    return float(raw) if "." in raw else int(raw)


def _field_path(name: str, position: int) -> str:
    if "__" in name:
        raise FilterExpressionError(
            f"Use dots instead of double underscores in field path {name!r}", position
        )
    segments = name.split(".")
    if any(segment.startswith("_") for segment in segments):
        raise FilterExpressionError(f"Field path {name!r} may not target private names", position)
    return "__".join(segments)


class _Parser:
    """A recursive descent parser producing ``Q`` objects."""

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self) -> Q:
        node = self._parse_or()
        token = self._peek()
        if token.kind != "end":
            raise FilterExpressionError(f"Unexpected {token.value!r}", token.position)
        return node

    # -- plumbing ---------------------------------------------------------
    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _match_keyword(self, keyword: str) -> bool:
        token = self._peek()
        if token.kind == "name" and token.value.lower() == keyword:
            self._advance()
            return True
        return False

    def _expect(self, kind: str) -> Token:
        token = self._peek()
        if token.kind != kind:
            raise FilterExpressionError(f"Expected {kind}, found {token.value!r}", token.position)
        return self._advance()

    # -- grammar ----------------------------------------------------------
    def _parse_or(self) -> Q:
        node = self._parse_and()
        while self._match_keyword("or"):
            node |= self._parse_and()
        return node

    def _parse_and(self) -> Q:
        node = self._parse_unary()
        while self._match_keyword("and"):
            node &= self._parse_unary()
        return node

    def _parse_unary(self) -> Q:
        if self._match_keyword("not"):
            return ~self._parse_unary()
        if self._peek().kind == "lparen":
            self._advance()
            node = self._parse_or()
            self._expect("rparen")
            return node
        return self._parse_comparison()

    def _parse_comparison(self) -> Q:
        name = self._expect("name")
        if name.value.lower() in KEYWORDS:
            raise FilterExpressionError(f"{name.value!r} is a reserved word", name.position)
        path = _field_path(name.value, name.position)
        lookup, negated = self._parse_operator()
        value = self._parse_value()
        condition = Q(**{f"{path}__{lookup}": value})
        return ~condition if negated else condition

    def _parse_operator(self) -> tuple[str, bool]:
        token = self._peek()
        if token.kind == "operator":
            self._advance()
            return SYMBOL_LOOKUPS[token.value]
        if token.kind == "name":
            negated = token.value.lower() == "not"
            if negated:
                self._advance()
                token = self._peek()
            if token.kind == "name" and token.value.lower() in NAMED_LOOKUPS:
                self._advance()
                return token.value.lower(), negated
        raise FilterExpressionError(f"Expected an operator, found {token.value!r}", token.position)

    def _parse_value(self) -> Any:
        token = self._advance()
        if token.kind == "string":
            return _parse_string(token.value)
        if token.kind == "number":
            return _parse_number(token.value)
        if token.kind == "name" and token.value.lower() in LITERALS:
            return LITERALS[token.value.lower()]
        if token.kind == "lbracket":
            return self._parse_list()
        raise FilterExpressionError(f"Expected a value, found {token.value!r}", token.position)

    def _parse_list(self) -> list[Any]:
        items: list[Any] = []
        if self._peek().kind == "rbracket":
            self._advance()
            return items
        while True:
            items.append(self._parse_value())
            token = self._advance()
            if token.kind == "rbracket":
                return items
            if token.kind != "comma":
                raise FilterExpressionError(
                    f"Expected ',' or ']', found {token.value!r}", token.position
                )


def compile_filter_expression(expression: str) -> Q:
    """Compile *expression* into a ``Q`` object; an empty string means "no filter"."""
    if not expression.strip():
        return Q()
    return _Parser(tokenize(expression)).parse()


def validate_filter_expression(expression: str) -> None:
    """Raise ``ValidationError`` when *expression* cannot be compiled."""
    try:
        compile_filter_expression(expression)
    except FilterExpressionError as exc:
        raise ValidationError(
            _("Invalid filter expression: %(error)s"),
            code="invalid_filter_expression",
            params={"error": str(exc)},
        ) from exc
