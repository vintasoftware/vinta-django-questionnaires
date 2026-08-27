"""Files.

A file answer is an object with at least ``size`` and ``content_type`` -- what
an upload endpoint hands back -- or a list of them for a multi-file question.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.question_types import FILE_TYPES
from vinta_django_questionnaires.validators.base import (
    BaseValidator,
    Case,
    Check,
    ClientSpec,
    ValidationContext,
    ValidatorOutput,
)
from vinta_django_questionnaires.validators.coercion import as_files
from vinta_django_questionnaires.validators.registry import register_validator

INVALID_TYPE = {"invalid_type": _("Attach a file.")}


class FileValidator(BaseValidator):
    supported_question_types = FILE_TYPES

    def files(self, value: Any) -> list[dict[str, Any]]:
        files = as_files(value)
        if files is None:
            self.fail("invalid_type")
        return files


@register_validator
class MaxFileSizeValidator(FileValidator):
    key = "max_file_size"
    label = _("Maximum file size")
    error_messages = {
        **INVALID_TYPE,
        "file_too_large": _("{name} is over the {max_bytes} byte limit."),
    }
    params_schema = {
        "type": "object",
        "properties": {"max_bytes": {"type": "integer", "exclusiveMinimum": 0}},
        "required": ["max_bytes"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("file.maxSize", error_key="file_too_large", args=("max_bytes",))
    )
    conformance = (
        Case(
            value={"name": "a.pdf", "size": 1000, "content_type": "application/pdf"},
            params={"max_bytes": 2000},
            question_type="single_file",
        ),
        Case(
            value={"name": "a.pdf", "size": 4000, "content_type": "application/pdf"},
            params={"max_bytes": 2000},
            question_type="single_file",
            expects=("file_too_large",),
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        for uploaded in self.files(value):
            if int(uploaded.get("size") or 0) > self.params["max_bytes"]:
                self.fail(
                    "file_too_large",
                    name=uploaded.get("name", ""),
                    max_bytes=self.params["max_bytes"],
                )
        return None


@register_validator
class AllowedContentTypesValidator(FileValidator):
    key = "allowed_content_types"
    label = _("Allowed file types")
    error_messages = {
        **INVALID_TYPE,
        "unsupported_file_type": _("{name} is not an accepted file type."),
    }
    params_schema = {
        "type": "object",
        "properties": {
            "content_types": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        },
        "required": ["content_types"],
        "additionalProperties": False,
    }
    client = ClientSpec.native(
        Check("file.contentType", error_key="unsupported_file_type", args=("content_types",))
    )
    conformance = (
        Case(
            value={"name": "a.pdf", "size": 10, "content_type": "application/pdf"},
            params={"content_types": ["application/pdf"]},
            question_type="single_file",
        ),
        Case(
            value={"name": "a.png", "size": 10, "content_type": "image/png"},
            params={"content_types": ["application/pdf"]},
            question_type="single_file",
            expects=("unsupported_file_type",),
        ),
        Case(
            value={"name": "a.png", "size": 10, "content_type": "image/png"},
            params={"content_types": ["image/*"]},
            question_type="single_file",
            label="wildcards match a whole family",
        ),
    )

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        patterns = self.params["content_types"]
        for uploaded in self.files(value):
            content_type = str(uploaded.get("content_type") or "")
            if not any(self._matches(content_type, pattern) for pattern in patterns):
                self.fail("unsupported_file_type", name=uploaded.get("name", ""))
        return None

    @staticmethod
    def _matches(content_type: str, pattern: str) -> bool:
        if pattern.endswith("/*"):
            return content_type.startswith(pattern[:-1])
        return content_type == pattern
