"""JSON Schema helpers.

Widget props and validator params are both free-form JSON constrained by a
schema, so the two use cases share the same pair of helpers: one that checks a
schema is a schema, one that checks a document against it.
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def permissive_object_schema() -> dict[str, Any]:
    """The default schema for a widget that does not constrain its props."""
    return {"type": "object", "additionalProperties": True}


def validate_json_schema(schema: Any) -> None:
    """Raise ``ValidationError`` unless *schema* is a valid JSON Schema."""
    if not isinstance(schema, dict):
        raise ValidationError(_("A JSON Schema must be an object."), code="invalid_schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(
            _("Invalid JSON Schema: %(error)s"),
            code="invalid_schema",
            params={"error": exc.message},
        ) from exc


def validate_against_schema(value: Any, schema: dict[str, Any]) -> None:
    """Raise ``ValidationError`` listing every way *value* breaks *schema*."""
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: [str(part) for part in error.path],
    )
    if not errors:
        return
    raise ValidationError(
        [
            ValidationError(
                _("%(path)s: %(message)s"),
                code="schema_mismatch",
                params={
                    "path": "/".join(str(part) for part in error.path) or _("(root)"),
                    "message": error.message,
                },
            )
            for error in errors
        ]
    )
