"""Numbers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import NUMERIC_TYPES
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.coercion import as_decimal, as_number
from vinta_django_questionnaires.validators.registry import register_validator

INVALID_TYPE = {"invalid_type": _("Enter a number.")}


class NumberValidator(BaseValidator):
    """Base for the validators that need the answer to be a number."""

    supported_question_types = NUMERIC_TYPES

    def number(self, value: Any) -> float:
        number = as_number(value)
        if number is None:
            self.fail("invalid_type")
        return number


@register_validator
class MinValueValidator(NumberValidator):
    key = "min_value"
    label = _("Minimum value")
    error_messages = {**INVALID_TYPE, "too_small": _("Enter {minimum} or more.")}
    params_schema = {
        "type": "object",
        "properties": {"minimum": {"type": "number"}, "exclusive": {"type": "boolean"}},
        "required": ["minimum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("number.gte", error_key="too_small", args=("minimum",)))
    conformance = (
        Case(value=5, params={"minimum": 5}, question_type="number"),
        Case(value=4, params={"minimum": 5}, question_type="number", expects=("too_small",)),
        Case(
            value=5,
            params={"minimum": 5, "exclusive": True},
            question_type="number",
            expects=("too_small",),
        ),
    )

    def client_checks(self) -> list[dict[str, Any]]:
        kind = "number.gt" if self.params.get("exclusive") else "number.gte"
        return [self.emit_check(kind, "too_small", [self.params["minimum"]])]

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        number = self.number(value)
        minimum = float(self.params["minimum"])
        too_small = number <= minimum if self.params.get("exclusive") else number < minimum
        if too_small:
            self.fail("too_small", minimum=self.params["minimum"])
        return None


@register_validator
class MaxValueValidator(NumberValidator):
    key = "max_value"
    label = _("Maximum value")
    error_messages = {**INVALID_TYPE, "too_large": _("Enter {maximum} or less.")}
    params_schema = {
        "type": "object",
        "properties": {"maximum": {"type": "number"}, "exclusive": {"type": "boolean"}},
        "required": ["maximum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("number.lte", error_key="too_large", args=("maximum",)))
    conformance = (
        Case(value=5, params={"maximum": 5}, question_type="number"),
        Case(value=6, params={"maximum": 5}, question_type="number", expects=("too_large",)),
        Case(
            value=5,
            params={"maximum": 5, "exclusive": True},
            question_type="number",
            expects=("too_large",),
        ),
    )

    def client_checks(self) -> list[dict[str, Any]]:
        kind = "number.lt" if self.params.get("exclusive") else "number.lte"
        return [self.emit_check(kind, "too_large", [self.params["maximum"]])]

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        number = self.number(value)
        maximum = float(self.params["maximum"])
        too_large = number >= maximum if self.params.get("exclusive") else number > maximum
        if too_large:
            self.fail("too_large", maximum=self.params["maximum"])
        return None


@register_validator
class IntegerValidator(NumberValidator):
    key = "integer"
    label = _("Whole number")
    error_messages = {**INVALID_TYPE, "not_integer": _("Enter a whole number.")}
    client = ClientSpec.native(Check("number.int", error_key="not_integer"))
    conformance = (
        Case(value=3, question_type="number"),
        Case(value=3.5, question_type="number", expects=("not_integer",)),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        number = self.number(value)
        if number != int(number):
            self.fail("not_integer")
        return None


@register_validator
class MultipleOfValidator(NumberValidator):
    key = "multiple_of"
    label = _("Multiple of")
    error_messages = {**INVALID_TYPE, "not_multiple_of": _("Enter a multiple of {step}.")}
    params_schema = {
        "type": "object",
        "properties": {"step": {"type": "number", "exclusiveMinimum": 0}},
        "required": ["step"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("number.multipleOf", error_key="not_multiple_of", args=("step",))
    )
    conformance = (
        Case(value=15, params={"step": 5}, question_type="number"),
        Case(value=16, params={"step": 5}, question_type="number", expects=("not_multiple_of",)),
        Case(value=0.3, params={"step": 0.1}, question_type="number", label="decimals are exact"),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        self.number(value)
        amount = as_decimal(value)
        step = as_decimal(self.params["step"])
        if amount is None or step is None or amount % step != Decimal(0):
            self.fail("not_multiple_of", step=self.params["step"])
        return None
