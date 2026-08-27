"""Client-side widgets, and the props schema each one accepts."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import MARKDOWN_HELP, BaseModel
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.schemas import (
    permissive_object_schema,
    validate_against_schema,
    validate_json_schema,
)


class QuestionnaireWidget(BaseModel):
    """A widget a question can be rendered with.

    The server does not render anything: it stores the key the client maps to a
    component, and the JSON Schema that says which props that component takes.
    ``Question.widget_props`` is checked against this schema on every save.
    """

    key = models.SlugField(_("key"), max_length=100, unique=True)
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    component = models.CharField(
        _("component"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Identifier of the client-side component, when it differs from the key."),
    )
    props_schema = models.JSONField(
        _("props schema"),
        default=permissive_object_schema,
        help_text=_("JSON Schema (draft 2020-12) the question's widget props must satisfy."),
    )
    default_props = models.JSONField(_("default props"), default=dict, blank=True)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("questionnaire widget")
        verbose_name_plural = _("questionnaire widgets")
        ordering = ["key"]

    def __str__(self) -> str:
        return self.name or self.key

    def clean(self) -> None:
        super().clean()
        try:
            validate_json_schema(self.props_schema)
        except ValidationError as exc:
            raise ValidationError({"props_schema": exc}) from exc
        if self.default_props:
            try:
                self.validate_props(self.default_props)
            except ValidationError as exc:
                raise ValidationError({"default_props": exc}) from exc

    def validate_props(self, props: Any) -> None:
        """Raise ``ValidationError`` unless *props* satisfy ``props_schema``."""
        validate_against_schema(props, dict(self.props_schema or {}))

    def supports(self, question_type: str) -> bool:
        return self.question_type_supports.filter(question_type=question_type).exists()

    def resolve_props(self, props: dict[str, Any] | None) -> dict[str, Any]:
        """The widget's defaults, overridden by the question's own props."""
        return {**(self.default_props or {}), **(props or {})}

    @classmethod
    def default_for(cls, question_type: str) -> QuestionnaireWidget | None:
        """The widget used when a question of *question_type* names none."""
        support = (
            WidgetQuestionType.objects.filter(question_type=question_type, is_default=True)
            .select_related("widget")
            .first()
        )
        return support.widget if support else None


class WidgetQuestionType(BaseModel):
    """Says that a widget can render a question type -- and if it is the default."""

    widget = models.ForeignKey(
        QuestionnaireWidget,
        on_delete=models.CASCADE,
        related_name="question_type_supports",
        verbose_name=_("widget"),
    )
    question_type = models.CharField(
        _("question type"), max_length=50, choices=QuestionType.choices
    )
    is_default = models.BooleanField(
        _("is default"),
        default=False,
        help_text=_("Used by questions of this type that do not name a widget."),
    )

    class Meta:
        verbose_name = _("widget question type")
        verbose_name_plural = _("widget question types")
        ordering = ["widget", "question_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["widget", "question_type"], name="unique_question_type_per_widget"
            ),
            models.UniqueConstraint(
                fields=["question_type"],
                condition=Q(is_default=True),
                name="unique_default_widget_per_question_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.widget_id}: {self.question_type}"
