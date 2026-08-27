"""Lists and allowed values."""

from __future__ import annotations

import json
from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import MULTI_VALUE_TYPES
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.coercion import as_sequence
from vinta_django_questionnaires.validators.registry import register_validator

INVALID_TYPE = {"invalid_type": _("Enter a list of values.")}


class SequenceValidator(BaseValidator):
    supported_question_types = MULTI_VALUE_TYPES

    def items(self, value: Any) -> list[Any]:
        items = as_sequence(value)
        if items is None:
            self.fail("invalid_type")
        return items


@register_validator
class MinItemsValidator(SequenceValidator):
    key = "min_items"
    label = _("Minimum items")
    error_messages = {**INVALID_TYPE, "too_few_items": _("Choose at least {minimum}.")}
    params_schema = {
        "type": "object",
        "properties": {"minimum": {"type": "integer", "minimum": 0}},
        "required": ["minimum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("array.min", error_key="too_few_items", args=("minimum",)))
    conformance = (
        Case(value=["a", "b"], params={"minimum": 2}, question_type="multiple_choice"),
        Case(
            value=["a"],
            params={"minimum": 2},
            question_type="multiple_choice",
            expects=("too_few_items",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        items = self.items(value)
        if len(items) < self.params["minimum"]:
            self.fail("too_few_items", minimum=self.params["minimum"])
        return ValidatorOutput(value=items, data={"count": len(items)})


@register_validator
class MaxItemsValidator(SequenceValidator):
    key = "max_items"
    label = _("Maximum items")
    error_messages = {**INVALID_TYPE, "too_many_items": _("Choose at most {maximum}.")}
    params_schema = {
        "type": "object",
        "properties": {"maximum": {"type": "integer", "minimum": 0}},
        "required": ["maximum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("array.max", error_key="too_many_items", args=("maximum",)))
    conformance = (
        Case(value=["a", "b"], params={"maximum": 2}, question_type="multiple_choice"),
        Case(
            value=["a", "b", "c"],
            params={"maximum": 2},
            question_type="multiple_choice",
            expects=("too_many_items",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        items = self.items(value)
        if len(items) > self.params["maximum"]:
            self.fail("too_many_items", maximum=self.params["maximum"])
        return ValidatorOutput(value=items, data={"count": len(items)})


@register_validator
class UniqueItemsValidator(SequenceValidator):
    key = "unique_items"
    label = _("No duplicates")
    error_messages = {**INVALID_TYPE, "duplicate_items": _("Every entry must be different.")}
    client = ClientSpec.native(Check("array.unique", error_key="duplicate_items"))
    conformance = (
        Case(value=["a", "b"], question_type="multiple_choice"),
        Case(value=["a", "a"], question_type="multiple_choice", expects=("duplicate_items",)),
        Case(
            value=[{"x": 1}, {"x": 1}],
            question_type="item_list",
            expects=("duplicate_items",),
            label="entries compare by content, not identity",
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        items = self.items(value)
        seen = {json.dumps(item, sort_keys=True, default=str) for item in items}
        if len(seen) != len(items):
            self.fail("duplicate_items")
        return None


@register_validator
class OneOfValidator(BaseValidator):
    """Every answer, or every entry of a list answer, must be an allowed value."""

    key = "one_of"
    label = _("Allowed values")
    error_messages = {"not_allowed": _("{value} is not one of the allowed values.")}
    params_schema = {
        "type": "object",
        "properties": {"values": {"type": "array", "items": {}, "minItems": 1}},
        "required": ["values"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("value.oneOf", error_key="not_allowed", args=("values",)))
    conformance = (
        Case(value="red", params={"values": ["red", "blue"]}, question_type="single_choice"),
        Case(
            value="green",
            params={"values": ["red", "blue"]},
            question_type="single_choice",
            expects=("not_allowed",),
        ),
        Case(
            value=["red", "green"],
            params={"values": ["red", "blue"]},
            question_type="multiple_choice",
            expects=("not_allowed",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        allowed = self.params["values"]
        candidates = as_sequence(value)
        for candidate in candidates if candidates is not None else [value]:
            if candidate not in allowed:
                self.fail("not_allowed", value=candidate)
        return None
