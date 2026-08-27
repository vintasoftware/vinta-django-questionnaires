"""Validators this project adds to the ones the package ships.

The app config autodiscovers this module, so importing it is what registers
them -- the same way admin classes are picked up.
"""

from __future__ import annotations

from typing import Any

from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.validators import (
    BaseValidator,
    Case,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
    register_validator,
)

FREE_PROVIDERS = frozenset(
    {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "proton.me"}
)


@register_validator
class BusinessEmailValidator(BaseValidator):
    """A work address, not a personal one.

    ``ClientSpec.custom()`` means the browser needs its own implementation
    registered under the same key.  Until one is, the client skips the check
    and says so through ``onDiagnostic``; the server still enforces it.
    """

    key = "business_email"
    label = "Business email"
    error_messages = {
        "invalid_type": "Enter an email address.",
        "personal_address": "Use your work address, not a {domain} one.",
    }
    supported_question_types = frozenset({QuestionType.FREE_TEXT})
    client = ClientSpec.custom()
    conformance = (
        Case(value="hugo@vinta.com.br"),
        Case(value="hugo@gmail.com", expects=("personal_address",)),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        if not isinstance(value, str) or "@" not in value:
            self.fail("invalid_type")
        domain = value.rsplit("@", 1)[-1].lower()
        if domain in FREE_PROVIDERS:
            self.fail("personal_address", domain=domain)
        return ValidatorOutput(value=value, data={"domain": domain})


@register_validator
class UniqueCompanyNameValidator(BaseValidator):
    """No two responses may name the same company.

    ``ClientSpec.server_only()`` is for checks a browser cannot make.  The
    client marks it as checked on submit rather than pretending to run it.
    """

    key = "unique_company_name"
    label = "Company not already registered"
    error_messages = {"already_registered": "{value} has already been registered."}
    supported_question_types = frozenset({QuestionType.FREE_TEXT})
    client = ClientSpec.server_only()
    conformance = (Case(value="Vinta Software"),)

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        from vinta_django_questionnaires.models import Answer

        # The response being filled in arrives under `extra`, so its own answer
        # from a previous submission does not count against it.
        response = context.extra.get("response")
        taken = Answer.objects.filter(question__key="company_name", value=value)
        if response is not None:
            taken = taken.exclude(response=response)
        if taken.exists():
            self.fail("already_registered", value=value)
        return None
