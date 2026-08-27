"""Abstract bases shared by the questionnaire models."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.conditions import evaluate_condition, validate_condition

#: Reused by every rich-text field so the admin says the same thing everywhere.
MARKDOWN_HELP = _("Markdown is supported.")


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True, editable=False)

    class Meta:
        abstract = True


class ValidatedModel(models.Model):
    """Runs ``full_clean()`` on every save.

    Questionnaire definitions are written rarely and read constantly, and much
    of what makes one valid -- widget props matching their schema, conditions
    that parse, validators that exist -- lives in ``clean()``.  Paying for that
    on save is what keeps invalid definitions out of the database.  Pass
    ``validate=False`` from data migrations and fixtures that know better.
    """

    class Meta:
        abstract = True

    def save(self, *args: Any, validate: bool = True, **kwargs: Any) -> None:
        if validate:
            self.full_clean()
        super().save(*args, **kwargs)


class BaseModel(TimeStampedModel, ValidatedModel):
    class Meta:
        abstract = True


class ConditionalMixin(models.Model):
    """A layer that only counts when its condition holds.

    The condition is a JMESPath expression evaluated at run time against the
    answers collected so far.  When it resolves to something falsy the layer is
    skipped: not rendered, not validated, not saved.
    """

    condition = models.TextField(
        _("condition"),
        blank=True,
        default="",
        help_text=_(
            "JMESPath expression returning a boolean, evaluated against the answers. "
            "Leave empty to always include this item."
        ),
    )

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        try:
            validate_condition(self.condition)
        except ValidationError as exc:
            raise ValidationError({"condition": exc}) from exc

    def is_applicable(self, answers: Any) -> bool:
        """Whether this layer should be considered for *answers*."""
        return evaluate_condition(self.condition, answers)
