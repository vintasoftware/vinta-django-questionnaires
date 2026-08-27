"""The dynamic validation layer.

Validators are registered under a key, which is also the key the client-side
implementation registers under -- one identity, two runtimes.  The built-ins
are registered on import; other Django apps add their own with the decorator,
from a ``questionnaire_validators`` module the app config autodiscovers.
"""

from __future__ import annotations

from vinta_django_questionnaires.validators import builtins  # noqa: F401  -- registration
from vinta_django_questionnaires.validators.base import (
    CLIENT_MODE_CHECKS,
    CLIENT_MODE_CUSTOM,
    CLIENT_MODE_SERVER_ONLY,
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidationIssue,
    ValidatorFailure,
    ValidatorOutcome,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.registry import (
    ValidatorAlreadyRegistered,
    ValidatorNotRegistered,
    ValidatorRegistry,
    register_validator,
    registry,
    validate_validator_key,
)

__all__ = [
    "CLIENT_MODE_CHECKS",
    "CLIENT_MODE_CUSTOM",
    "CLIENT_MODE_SERVER_ONLY",
    "BaseValidator",
    "Case",
    "Check",
    "ClientSpec",
    "ValidationContext",
    "ValidationIssue",
    "ValidatorAlreadyRegistered",
    "ValidatorFailure",
    "ValidatorNotRegistered",
    "ValidatorOutcome",
    "ValidatorOutput",
    "ValidatorRegistry",
    "register_validator",
    "registry",
    "validate_validator_key",
]
