"""Run-time conditions attached to pages, sections and questions.

A condition is a JMESPath expression evaluated against the data collected for a
questionnaire.  When it resolves to a falsy value, the layer that owns it is
skipped -- it is neither rendered nor considered for validation and saving.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

import jmespath
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from jmespath.exceptions import JMESPathError

if TYPE_CHECKING:
    from jmespath.parser import ParsedResult


class ConditionEvaluationError(RuntimeError):
    """Raised when a syntactically valid condition blows up on real data."""

    def __init__(self, expression: str, error: Exception) -> None:
        super().__init__(f"Could not evaluate condition {expression!r}: {error}")
        self.expression = expression
        self.error = error


@lru_cache(maxsize=1024)
def compile_condition(expression: str) -> ParsedResult:
    """Compile -- and memoise -- a JMESPath expression."""
    return jmespath.compile(expression)


def validate_condition(expression: str) -> None:
    """Raise ``ValidationError`` when *expression* is not valid JMESPath.

    An empty expression is valid: it means "always applicable".
    """
    if not expression.strip():
        return
    try:
        compile_condition(expression)
    except JMESPathError as exc:
        raise ValidationError(
            _("%(expression)s is not a valid JMESPath expression: %(error)s"),
            code="invalid_condition",
            params={"expression": expression, "error": str(exc)},
        ) from exc


def evaluate_condition(expression: str, data: Any, *, default: bool = True) -> bool:
    """Evaluate *expression* against *data* and coerce the result to a boolean.

    An empty expression returns *default*, so layers without a condition are
    always applicable.  JMESPath returns ``None`` for paths that are missing
    from the data, which makes partially filled questionnaires evaluate to
    ``False`` rather than raise.
    """
    if not expression.strip():
        return default
    try:
        return bool(compile_condition(expression).search(data))
    except JMESPathError as exc:
        raise ConditionEvaluationError(expression, exc) from exc
