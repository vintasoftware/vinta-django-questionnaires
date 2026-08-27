"""Presence."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.registry import register_validator


@register_validator
class RequiredValidator(BaseValidator):
    key = "required"
    label = _("Required")
    error_messages = {"required": _("This answer is required.")}
    skip_when_empty = False
    client = ClientSpec.native(Check("presence.required", error_key="required"))
    conformance = (
        Case(value=None, expects=("required",)),
        Case(value="", expects=("required",)),
        Case(value=[], expects=("required",), question_type=QuestionType.MULTIPLE_CHOICE),
        Case(value="Hugo"),
        Case(value=0, question_type=QuestionType.NUMBER, label="zero is an answer"),
        Case(value="no", question_type=QuestionType.SINGLE_CHOICE, label="a no is an answer"),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        if self.is_empty(value):
            self.fail("required")
        return None
