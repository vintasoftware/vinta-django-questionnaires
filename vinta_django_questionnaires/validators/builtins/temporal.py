"""Dates, times and ranges."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import RANGE_TYPES, TEMPORAL_TYPES
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.coercion import (
    as_number,
    as_range,
    as_temporal,
    comparable_temporals,
)
from vinta_django_questionnaires.validators.registry import register_validator

INVALID_TYPE = {"invalid_type": _("Enter a valid date or time.")}


class TemporalValidator(BaseValidator):
    supported_question_types = TEMPORAL_TYPES

    def bounds(self, value: Any, limit: Any) -> tuple[Any, Any]:
        pair = comparable_temporals(as_temporal(value), as_temporal(limit))
        if pair is None:
            self.fail("invalid_type")
        return pair


@register_validator
class MinDateValidator(TemporalValidator):
    key = "min_date"
    label = _("Not before")
    error_messages = {**INVALID_TYPE, "date_too_early": _("Choose {minimum} or later.")}
    params_schema = {
        "type": "object",
        "properties": {"minimum": {"type": "string"}},
        "required": ["minimum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("date.min", error_key="date_too_early", args=("minimum",)))
    conformance = (
        Case(value="2026-03-01", params={"minimum": "2026-01-01"}, question_type="date"),
        Case(
            value="2025-12-31",
            params={"minimum": "2026-01-01"},
            question_type="date",
            expects=("date_too_early",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        moment, minimum = self.bounds(value, self.params["minimum"])
        if moment < minimum:
            self.fail("date_too_early", minimum=self.params["minimum"])
        return None


@register_validator
class MaxDateValidator(TemporalValidator):
    key = "max_date"
    label = _("Not after")
    error_messages = {**INVALID_TYPE, "date_too_late": _("Choose {maximum} or earlier.")}
    params_schema = {
        "type": "object",
        "properties": {"maximum": {"type": "string"}},
        "required": ["maximum"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(Check("date.max", error_key="date_too_late", args=("maximum",)))
    conformance = (
        Case(value="2026-01-01", params={"maximum": "2026-12-31"}, question_type="date"),
        Case(
            value="2027-01-01",
            params={"maximum": "2026-12-31"},
            question_type="date",
            expects=("date_too_late",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        moment, maximum = self.bounds(value, self.params["maximum"])
        if moment > maximum:
            self.fail("date_too_late", maximum=self.params["maximum"])
        return None


@register_validator
class RangeOrderedValidator(BaseValidator):
    """A range answer must be complete, and its start must not follow its end."""

    key = "range_ordered"
    label = _("Ordered range")
    error_messages = {
        "invalid_type": _("Enter a range."),
        "incomplete_range": _("Enter both a start and an end."),
        "range_out_of_order": _("The start must come before the end."),
    }
    supported_question_types = RANGE_TYPES
    client = ClientSpec.native(Check("range.ordered", error_key="range_out_of_order"))
    conformance = (
        Case(
            value={"start": "2026-01-01", "end": "2026-02-01"},
            question_type="date_range",
        ),
        Case(
            value={"start": "2026-03-01", "end": "2026-02-01"},
            question_type="date_range",
            expects=("range_out_of_order",),
        ),
        Case(
            value={"start": "2026-03-01", "end": None},
            question_type="date_range",
            expects=("incomplete_range",),
        ),
        Case(value={"start": 1, "end": 10}, question_type="number_range"),
        Case(
            value={"start": 10, "end": 1},
            question_type="number_range",
            expects=("range_out_of_order",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        bounds = as_range(value)
        if bounds is None:
            self.fail("invalid_type")
        start, end = bounds
        if start is None or end is None:
            self.fail("incomplete_range")
        numbers = as_number(start), as_number(end)
        if None not in numbers:
            if numbers[0] > numbers[1]:  # type: ignore[operator]
                self.fail("range_out_of_order")
            return None
        pair = comparable_temporals(as_temporal(start), as_temporal(end))
        if pair is None:
            self.fail("invalid_type")
        if pair[0] > pair[1]:
            self.fail("range_out_of_order")
        return None
