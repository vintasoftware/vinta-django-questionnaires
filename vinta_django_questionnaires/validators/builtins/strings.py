"""Text.

``email``, ``url`` and ``uuid`` carry their pattern here rather than deferring
to Zod's own checks: the client's check table applies these very patterns, so
the two sides agree on the edge cases instead of on the happy path only.
"""

from __future__ import annotations

import re
from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import TEXTUAL_TYPES
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.coercion import as_text
from vinta_django_questionnaires.validators.registry import register_validator

#: Shared with the client's ``string.email`` check.
EMAIL_PATTERN = (
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
#: Shared with the client's ``string.url`` check: a scheme and a host.
URL_PATTERN = r"^[A-Za-z][A-Za-z0-9+.-]*://[^\s/?#]+[^\s]*$"
#: Shared with the client's ``string.uuid`` check.
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

INVALID_TYPE = {"invalid_type": _("Enter text.")}


class TextValidator(BaseValidator):
    """Base for the validators that need the answer to be text."""

    supported_question_types = TEXTUAL_TYPES

    def text(self, value: Any) -> str:
        text = as_text(value)
        if text is None:
            self.fail("invalid_type")
        return text


@register_validator
class MinLengthValidator(TextValidator):
    key = "min_length"
    label = _("Minimum length")
    error_messages = {**INVALID_TYPE, "too_short": _("Use at least {minimum} characters.")}
    params_schema = {
        "type": "object",
        "properties": {"minimum": {"type": "integer", "minimum": 0}},
        "required": ["minimum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("string.min", error_key="too_short", args=("minimum",)))
    conformance = (
        Case(value="ab", params={"minimum": 3}, expects=("too_short",)),
        Case(value="abc", params={"minimum": 3}),
        Case(value="", params={"minimum": 3}, label="empty answers skip the check"),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        text = self.text(value)
        if len(text) < self.params["minimum"]:
            self.fail("too_short", minimum=self.params["minimum"])
        return ValidatorOutput(value=text, data={"length": len(text)})


@register_validator
class MaxLengthValidator(TextValidator):
    key = "max_length"
    label = _("Maximum length")
    error_messages = {**INVALID_TYPE, "too_long": _("Use at most {maximum} characters.")}
    params_schema = {
        "type": "object",
        "properties": {"maximum": {"type": "integer", "minimum": 0}},
        "required": ["maximum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("string.max", error_key="too_long", args=("maximum",)))
    conformance = (
        Case(value="abcd", params={"maximum": 3}, expects=("too_long",)),
        Case(value="abc", params={"maximum": 3}),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        text = self.text(value)
        if len(text) > self.params["maximum"]:
            self.fail("too_long", maximum=self.params["maximum"])
        return ValidatorOutput(value=text, data={"length": len(text)})


@register_validator
class PatternValidator(TextValidator):
    key = "pattern"
    label = _("Pattern")
    error_messages = {**INVALID_TYPE, "pattern_mismatch": _("This value has the wrong format.")}
    params_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "ignore_case": {"type": "boolean"},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("string.regex", error_key="pattern_mismatch", args=("pattern", "ignore_case"))
    )
    conformance = (
        Case(value="AB12", params={"pattern": "^[A-Z]{2}[0-9]{2}$"}),
        Case(
            value="ab12", params={"pattern": "^[A-Z]{2}[0-9]{2}$"}, expects=("pattern_mismatch",)
        ),
        Case(value="ab12", params={"pattern": "^[A-Z]{2}[0-9]{2}$", "ignore_case": True}),
    )

    def check_args(self, check: Check) -> list[Any]:
        return [self.params["pattern"], bool(self.params.get("ignore_case", False))]

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        text = self.text(value)
        flags = re.IGNORECASE if self.params.get("ignore_case") else 0
        if re.search(self.params["pattern"], text, flags) is None:
            self.fail("pattern_mismatch", pattern=self.params["pattern"])
        return None


class _FormatValidator(TextValidator):
    """A pattern the client applies through the same expression."""

    pattern: str = ""
    error_key: str = ""

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        text = self.text(value)
        if re.match(self.pattern, text) is None:
            self.fail(self.error_key)
        return None


@register_validator
class EmailValidator(_FormatValidator):
    key = "email"
    label = _("Email")
    error_messages = {**INVALID_TYPE, "invalid_email": _("Enter a valid email address.")}
    pattern = EMAIL_PATTERN
    error_key = "invalid_email"
    client = ClientSpec.native(Check("string.email", error_key="invalid_email"))
    conformance = (
        Case(value="hugo@vinta.com.br"),
        Case(value="not-an-email", expects=("invalid_email",)),
        Case(value="hugo@localhost", expects=("invalid_email",), label="a host needs a dot"),
    )


@register_validator
class UrlValidator(_FormatValidator):
    key = "url"
    label = _("URL")
    error_messages = {**INVALID_TYPE, "invalid_url": _("Enter a valid URL.")}
    pattern = URL_PATTERN
    error_key = "invalid_url"
    client = ClientSpec.native(Check("string.url", error_key="invalid_url"))
    conformance = (
        Case(value="https://vinta.com.br/blog"),
        Case(value="vinta.com.br", expects=("invalid_url",), label="a scheme is required"),
    )


@register_validator
class UuidValidator(_FormatValidator):
    key = "uuid"
    label = _("UUID")
    error_messages = {**INVALID_TYPE, "invalid_uuid": _("Enter a valid UUID.")}
    pattern = UUID_PATTERN
    error_key = "invalid_uuid"
    client = ClientSpec.native(Check("string.uuid", error_key="invalid_uuid"))
    conformance = (
        Case(value="4f1a7c2e-9b3d-4e5f-8a6b-0c1d2e3f4a5b"),
        Case(value="4f1a7c2e", expects=("invalid_uuid",)),
    )


@register_validator
class StartsWithValidator(TextValidator):
    key = "starts_with"
    label = _("Starts with")
    error_messages = {**INVALID_TYPE, "not_starts_with": _("This must start with {prefix}.")}
    params_schema = {
        "type": "object",
        "properties": {"prefix": {"type": "string"}},
        "required": ["prefix"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("string.startsWith", error_key="not_starts_with", args=("prefix",))
    )
    conformance = (
        Case(value="PR-1", params={"prefix": "PR-"}),
        Case(value="XX-1", params={"prefix": "PR-"}, expects=("not_starts_with",)),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        if not self.text(value).startswith(self.params["prefix"]):
            self.fail("not_starts_with", prefix=self.params["prefix"])
        return None


@register_validator
class EndsWithValidator(TextValidator):
    key = "ends_with"
    label = _("Ends with")
    error_messages = {**INVALID_TYPE, "not_ends_with": _("This must end with {suffix}.")}
    params_schema = {
        "type": "object",
        "properties": {"suffix": {"type": "string"}},
        "required": ["suffix"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("string.endsWith", error_key="not_ends_with", args=("suffix",))
    )
    conformance = (
        Case(value="report.pdf", params={"suffix": ".pdf"}),
        Case(value="report.doc", params={"suffix": ".pdf"}, expects=("not_ends_with",)),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        if not self.text(value).endswith(self.params["suffix"]):
            self.fail("not_ends_with", suffix=self.params["suffix"])
        return None


@register_validator
class IncludesValidator(TextValidator):
    key = "includes"
    label = _("Includes")
    error_messages = {**INVALID_TYPE, "does_not_include": _("This must contain {substring}.")}
    params_schema = {
        "type": "object",
        "properties": {"substring": {"type": "string"}},
        "required": ["substring"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("string.includes", error_key="does_not_include", args=("substring",))
    )
    conformance = (
        Case(value="a big cat", params={"substring": "big"}),
        Case(value="a small cat", params={"substring": "big"}, expects=("does_not_include",)),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        if self.params["substring"] not in self.text(value):
            self.fail("does_not_include", substring=self.params["substring"])
        return None
