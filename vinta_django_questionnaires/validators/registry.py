"""The registry validator keys resolve against."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.schemas import validate_json_schema

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.utils.functional import Promise

    from vinta_django_questionnaires.validators.base import BaseValidator


class ValidatorNotRegistered(KeyError):
    """Raised when a question references a validator key nobody registered."""


class ValidatorAlreadyRegistered(ValueError):
    """Raised when two validator classes claim the same key."""


class ValidatorRegistry:
    """The process-wide map of validator key to validator class."""

    def __init__(self) -> None:
        self._validators: dict[str, type[BaseValidator]] = {}

    def register(
        self,
        validator_class: type[BaseValidator],
        *,
        key: str | None = None,
        force: bool = False,
    ) -> type[BaseValidator]:
        resolved_key = key or validator_class.key
        if not resolved_key:
            raise ValueError(f"{validator_class.__name__} must declare a non-empty key.")
        if not validator_class.error_messages:
            raise ValueError(
                f"{validator_class.__name__} must declare at least one error key with its message."
            )
        validate_json_schema(dict(validator_class.params_schema))
        existing = self._validators.get(resolved_key)
        if existing is not None and existing is not validator_class and not force:
            raise ValidatorAlreadyRegistered(
                f"{resolved_key!r} is already registered by {existing.__name__}."
            )
        validator_class.key = resolved_key
        self._validators[resolved_key] = validator_class
        return validator_class

    def unregister(self, key: str) -> None:
        self._validators.pop(key, None)

    def get(self, key: str) -> type[BaseValidator]:
        try:
            return self._validators[key]
        except KeyError:
            raise ValidatorNotRegistered(key) from None

    def __contains__(self, key: object) -> bool:
        return key in self._validators

    def __iter__(self) -> Iterator[str]:
        return iter(self._validators)

    def __len__(self) -> int:
        return len(self._validators)

    def items(self) -> list[tuple[str, type[BaseValidator]]]:
        return sorted(self._validators.items())

    def choices(self) -> list[tuple[str, Promise | str]]:
        """Choices for the ``QuestionValidator.validator`` form field."""
        return [(key, validator.label or key) for key, validator in self.items()]


#: The registry questions resolve their validator keys against.
registry = ValidatorRegistry()


def register_validator(
    validator_class: type[BaseValidator] | None = None,
    *,
    key: str | None = None,
    force: bool = False,
) -> Any:
    """Register a validator class.  Usable bare or with arguments."""

    def decorator(cls: type[BaseValidator]) -> type[BaseValidator]:
        return registry.register(cls, key=key, force=force)

    if validator_class is not None:
        return decorator(validator_class)
    return decorator


def validate_validator_key(key: str) -> type[BaseValidator]:
    """Resolve *key*, raising ``ValidationError`` when it is unknown."""
    try:
        return registry.get(key)
    except ValidatorNotRegistered as exc:
        raise ValidationError(
            _("There is no validator registered under the key %(key)s."),
            code="unknown_validator",
            params={"key": key},
        ) from exc
