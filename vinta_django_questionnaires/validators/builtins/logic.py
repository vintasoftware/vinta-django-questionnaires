"""Cross-field logic.

JMESPath is already how conditions are written, and it runs the same way in
Python and in the browser -- so a predicate written once needs no second
implementation to hold on both sides.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.conditions import compile_condition, validate_condition
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.registry import register_validator


def predicate_document(value: Any, context: ValidationContext) -> dict[str, Any]:
    """What a predicate expression is evaluated against, on both sides."""
    return {
        "value": value,
        "answers": context.answers,
        "extra": context.extra,
        "results": {
            outcome.validator: {"valid": outcome.is_valid, "data": outcome.data}
            for outcome in context.outcomes
        },
    }


@register_validator
class JMESPathPredicateValidator(BaseValidator):
    """Holds when *expression* evaluates to something truthy.

    The document carries the answer under ``value``, the whole answer set under
    ``answers``, and what the earlier links of the chain recorded under
    ``results`` -- which is what makes this the escape hatch for rules that
    depend on more than the answer itself.
    """

    key = "jmespath_predicate"
    label = _("Expression")
    error_messages = {"predicate_failed": _("This answer is not valid here.")}
    params_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string", "minLength": 1}},
        "required": ["expression"],
        "additionalProperties": False,
    }
    reads_context = True
    client = ClientSpec.native(
        Check("logic.jmespath", error_key="predicate_failed", args=("expression",))
    )
    conformance = (
        Case(value=10, params={"expression": "value > `5`"}, question_type="number"),
        Case(
            value=3,
            params={"expression": "value > `5`"},
            question_type="number",
            expects=("predicate_failed",),
        ),
        Case(
            value="x",
            params={"expression": "results.min_length.valid"},
            expects=("predicate_failed",),
            label="an absent earlier result is falsy",
        ),
    )

    @classmethod
    def check_params(cls, params: Any) -> None:
        super().check_params(params)
        if isinstance(params, dict) and params.get("expression"):
            try:
                validate_condition(str(params["expression"]))
            except ValidationError as exc:
                raise ValidationError({"expression": exc}) from exc

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        document = predicate_document(value, context)
        if not compile_condition(self.params["expression"]).search(document):
            self.fail("predicate_failed", expression=self.params["expression"])
        return None
