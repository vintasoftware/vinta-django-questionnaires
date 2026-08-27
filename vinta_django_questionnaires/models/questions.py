"""Questions, their choices, and the validator chain attached to them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import MARKDOWN_HELP, BaseModel, ConditionalMixin
from vinta_django_questionnaires.models.editing import VersionScopedModel
from vinta_django_questionnaires.models.layout import DEFAULT_COLUMN_COUNT, WindowSizeRange
from vinta_django_questionnaires.models.questionnaires import Questionnaire, QuestionnaireVersion
from vinta_django_questionnaires.models.structure import Section
from vinta_django_questionnaires.models.value_sets import ValueSet
from vinta_django_questionnaires.models.widgets import QuestionnaireWidget
from vinta_django_questionnaires.question_types import (
    SCALAR_TYPES,
    QuestionType,
    QuestionTypeSpec,
    get_question_type_spec,
)
from vinta_django_questionnaires.validators import (
    ValidationContext,
    validate_validator_key,
)

if TYPE_CHECKING:
    from vinta_django_questionnaires.validators import BaseValidator


class ChoiceAxis(models.TextChoices):
    """Which side of the question a choice belongs to."""

    OPTION = "option", _("Option")
    ROW = "row", _("Matrix row")
    COLUMN = "column", _("Matrix column")


class Question(ConditionalMixin, VersionScopedModel, BaseModel):
    """A single question inside a section.

    What a question may configure depends on its type, and the type table in
    ``question_types`` is what ``clean()`` checks it against: a free text
    question cannot carry choices, a sub-questionnaire question must name the
    questionnaire it nests, and so on.
    """

    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=_("section"),
    )
    key = models.SlugField(
        _("key"),
        max_length=100,
        help_text=_("Unique within the questionnaire version. Answers are keyed by it."),
    )
    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(
        _("description"), blank=True, default="", help_text=MARKDOWN_HELP
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    question_type = models.CharField(
        _("question type"), max_length=50, choices=QuestionType.choices
    )

    # -- layout ------------------------------------------------------------
    requires_being_first_in_a_row = models.BooleanField(
        _("requires being first in a row"), default=False
    )
    requires_being_last_in_a_row = models.BooleanField(
        _("requires being last in a row"), default=False
    )

    # -- rendering ---------------------------------------------------------
    widget = models.ForeignKey(
        QuestionnaireWidget,
        on_delete=models.PROTECT,
        related_name="questions",
        null=True,
        blank=True,
        verbose_name=_("widget"),
        help_text=_("Leave empty to use the default widget of the question type."),
    )
    widget_props = models.JSONField(
        _("widget props"),
        default=dict,
        blank=True,
        help_text=_("Checked against the widget's props schema on save."),
    )

    # -- options -----------------------------------------------------------
    allows_other = models.BooleanField(
        _("allows other"),
        default=False,
        help_text=_("Adds a free text escape hatch to a choice question."),
    )
    other_label = models.CharField(_("other label"), max_length=255, blank=True, default="")
    value_set = models.ForeignKey(
        ValueSet,
        on_delete=models.PROTECT,
        related_name="questions",
        null=True,
        blank=True,
        verbose_name=_("value set"),
    )
    item_question_type = models.CharField(
        _("item question type"),
        max_length=50,
        choices=QuestionType.choices,
        blank=True,
        default="",
        help_text=_("The type of each item of a list of items."),
    )

    # -- nesting -----------------------------------------------------------
    sub_questionnaire = models.ForeignKey(
        Questionnaire,
        on_delete=models.PROTECT,
        related_name="referencing_questions",
        null=True,
        blank=True,
        verbose_name=_("sub-questionnaire"),
    )
    sub_questionnaire_version = models.ForeignKey(
        QuestionnaireVersion,
        on_delete=models.PROTECT,
        related_name="referencing_questions",
        null=True,
        blank=True,
        verbose_name=_("sub-questionnaire version"),
        help_text=_("Pin a version, or leave empty to follow the latest published one."),
    )

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ["section", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "key"], name="unique_question_key_per_section"
            )
        ]

    def __str__(self) -> str:
        return self.title or self.key

    # -- type --------------------------------------------------------------
    @property
    def content_fingerprint(self) -> str:
        """A digest of what this question asks, stable across versions."""
        from vinta_django_questionnaires.fingerprints import question_fingerprint

        return question_fingerprint(self)

    @property
    def spec(self) -> QuestionTypeSpec:
        """What this question's type allows."""
        return get_question_type_spec(self.question_type)

    def get_questionnaire_version(self) -> QuestionnaireVersion:
        return self.section.page.questionnaire_version

    def get_edited_version(self) -> QuestionnaireVersion | None:
        return self.section.page.questionnaire_version if self.section_id else None

    # -- layout ------------------------------------------------------------
    def resolve_minimum_columns(self, window_size_range: WindowSizeRange) -> int:
        """The narrowest this question may be rendered in *window_size_range*."""
        entry = self.minimum_columns.filter(window_size_range=window_size_range).first()
        return entry.minimum_columns if entry is not None else DEFAULT_COLUMN_COUNT

    def minimum_column_layout(self) -> dict[str, int]:
        ranges = self.get_questionnaire_version().window_size_ranges.all()
        return {
            window_size_range.key: self.resolve_minimum_columns(window_size_range)
            for window_size_range in ranges
        }

    # -- rendering ---------------------------------------------------------
    @property
    def resolved_widget(self) -> QuestionnaireWidget | None:
        """The question's widget, or the default one for its type."""
        if self.widget_id is not None:
            return self.widget
        return QuestionnaireWidget.default_for(self.question_type)

    @property
    def resolved_widget_props(self) -> dict[str, Any]:
        widget = self.resolved_widget
        if widget is None:
            return dict(self.widget_props or {})
        return widget.resolve_props(self.widget_props)

    # -- nesting -----------------------------------------------------------
    @property
    def resolved_sub_questionnaire_version(self) -> QuestionnaireVersion | None:
        """The pinned version, or the latest published one of the target."""
        if self.sub_questionnaire_version_id is not None:
            return self.sub_questionnaire_version
        target = self.sub_questionnaire if self.sub_questionnaire_id else None
        if target is None:
            return None
        return target.latest_published_version

    # -- validation chain --------------------------------------------------
    def build_validators(self) -> list[BaseValidator]:
        """The validator chain, in the order it runs."""
        return [binding.build() for binding in self.validators.filter(is_enabled=True)]

    def run_validators(
        self,
        value: Any,
        *,
        answers: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ValidationContext:
        """Run the chain over *value*.

        Each validator receives the context carrying the outcome of every
        validator before it, and may hand a coerced value to the next one.
        """
        context = ValidationContext(question=self, answers=answers, extra=extra)
        current = value
        for validator in self.build_validators():
            current = validator.run(current, context).value
        return context

    # -- integrity ---------------------------------------------------------
    def clean(self) -> None:
        super().clean()
        if self.question_type not in QuestionType.values:
            return  # clean_fields() already reported the bad choice
        spec = self.spec
        errors: dict[str, Any] = {}

        self._check_key_is_unique_in_version(errors)
        self._check_options(spec, errors)
        self._check_nesting(spec, errors)
        self._check_widget(errors)

        if errors:
            raise ValidationError(errors)

    def _check_key_is_unique_in_version(self, errors: dict[str, Any]) -> None:
        if self.section_id is None or not self.key:
            return
        version_id = self.section.page.questionnaire_version_id
        clashes = (
            Question.objects.filter(
                section__page__questionnaire_version_id=version_id, key=self.key
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if clashes:
            errors["key"] = _("Another question of this version already uses this key.")

    def _check_options(self, spec: QuestionTypeSpec, errors: dict[str, Any]) -> None:
        if self.allows_other and not spec.supports_other_option:
            errors["allows_other"] = _("%(type)s questions do not take an other option.") % {
                "type": spec.label
            }
        if self.value_set_id is not None and not spec.supports_value_set:
            errors["value_set"] = _("%(type)s questions do not take a value set.") % {
                "type": spec.label
            }
        if self.value_set_id is None and spec.supports_value_set and not spec.supports_choices:
            errors["value_set"] = _("%(type)s questions need a value set.") % {"type": spec.label}
        if spec.requires_item_type:
            if not self.item_question_type:
                errors["item_question_type"] = _("A list of items needs the type of its items.")
            elif self.item_question_type not in SCALAR_TYPES:
                errors["item_question_type"] = _("Items must be of a single-value type.")
        elif self.item_question_type:
            errors["item_question_type"] = _("Only a list of items takes an item type.")
        if self.pk is not None and not spec.supports_choices and self.choices.exists():
            errors["question_type"] = _("%(type)s questions do not take choices.") % {
                "type": spec.label
            }

    def _check_nesting(self, spec: QuestionTypeSpec, errors: dict[str, Any]) -> None:
        if not spec.requires_sub_questionnaire:
            if self.sub_questionnaire_id is not None:
                errors["sub_questionnaire"] = _(
                    "Only sub-questionnaire questions nest another questionnaire."
                )
            return
        if self.sub_questionnaire_id is None:
            errors["sub_questionnaire"] = _("This question type needs a sub-questionnaire.")
            return
        pinned = self.sub_questionnaire_version if self.sub_questionnaire_version_id else None
        if pinned is not None and pinned.questionnaire_id != self.sub_questionnaire_id:
            errors["sub_questionnaire_version"] = _(
                "This version belongs to a different questionnaire."
            )
        if self.section_id is not None and self._nesting_loops_back():
            errors["sub_questionnaire"] = _(
                "Nesting this questionnaire would loop back to the one being edited."
            )

    def _nesting_loops_back(self) -> bool:
        """Whether following the nested questionnaires comes back here."""
        own_questionnaire_id = self.section.page.questionnaire_version.questionnaire_id
        pending = [self.sub_questionnaire_id]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current is None or current in seen:
                continue
            if current == own_questionnaire_id:
                return True
            seen.add(current)
            pending.extend(
                Question.objects.filter(
                    section__page__questionnaire_version__questionnaire_id=current,
                    sub_questionnaire__isnull=False,
                )
                .exclude(pk=self.pk)
                .values_list("sub_questionnaire_id", flat=True)
            )
        return False

    def _check_widget(self, errors: dict[str, Any]) -> None:
        own_widget = self.widget if self.widget_id else None
        if own_widget is not None and not own_widget.supports(self.question_type):
            errors["widget"] = _("%(widget)s does not support this question type.") % {
                "widget": own_widget
            }
            return
        widget = self.resolved_widget
        if widget is None:
            if self.widget_props:
                errors["widget_props"] = _(
                    "No widget is configured for this question type, so it takes no props."
                )
            return
        try:
            widget.validate_props(self.widget_props or {})
        except ValidationError as exc:
            errors["widget_props"] = exc


class QuestionChoice(VersionScopedModel, BaseModel):
    """An inline option of a choice question, or one axis entry of a matrix."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices",
        verbose_name=_("question"),
    )
    axis = models.CharField(
        _("axis"), max_length=10, choices=ChoiceAxis.choices, default=ChoiceAxis.OPTION
    )
    value = models.CharField(_("value"), max_length=255)
    label = models.CharField(_("label"), max_length=255)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    extra = models.JSONField(_("extra"), default=dict, blank=True)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("question choice")
        verbose_name_plural = _("question choices")
        ordering = ["question", "axis", "order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "axis", "value"], name="unique_choice_value_per_question_axis"
            )
        ]

    def __str__(self) -> str:
        return self.label or self.value

    def get_edited_version(self) -> QuestionnaireVersion | None:
        return self.question.get_questionnaire_version() if self.question_id else None

    def edit_key(self) -> str:
        return f"{self.question.key}.{self.value}" if self.question_id else self.value

    def clean(self) -> None:
        super().clean()
        if not self.question_id:
            return
        spec = self.question.spec
        if not spec.supports_choices:
            raise ValidationError(
                {"question": _("%(type)s questions do not take choices.") % {"type": spec.label}}
            )
        is_axis_entry = self.axis != ChoiceAxis.OPTION
        if is_axis_entry and not spec.uses_matrix_axes:
            raise ValidationError({"axis": _("Only a matrix question has rows and columns.")})
        if not is_axis_entry and spec.uses_matrix_axes:
            raise ValidationError({"axis": _("A matrix question takes rows and columns only.")})


class QuestionValidator(VersionScopedModel, BaseModel):
    """One link of a question's validator chain.

    The key resolves against the validator registry, the params against that
    validator's params schema, and the message overrides against the error keys
    it declares -- all on save, so a question can never reference a validator
    that is not there or configure it in a way it does not accept.
    """

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="validators",
        verbose_name=_("question"),
    )
    validator = models.CharField(
        _("validator"), max_length=100, help_text=_("Key the validator is registered under.")
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    params = models.JSONField(_("params"), default=dict, blank=True)
    message_overrides = models.JSONField(
        _("message overrides"),
        default=dict,
        blank=True,
        help_text=_("Maps one of the validator's error keys to the message to show instead."),
    )
    is_enabled = models.BooleanField(_("is enabled"), default=True)

    class Meta:
        verbose_name = _("question validator")
        verbose_name_plural = _("question validators")
        ordering = ["question", "order", "pk"]

    def __str__(self) -> str:
        return self.validator

    def get_edited_version(self) -> QuestionnaireVersion | None:
        return self.question.get_questionnaire_version() if self.question_id else None

    def edit_key(self) -> str:
        return f"{self.question.key}.{self.validator}" if self.question_id else self.validator

    @property
    def validator_class(self) -> type[BaseValidator]:
        """The registered class, raising ``ValidationError`` when unknown."""
        return validate_validator_key(self.validator)

    def build(self) -> BaseValidator:
        """Instantiate the validator with this question's configuration."""
        return self.validator_class(params=self.params, message_overrides=self.message_overrides)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, Any] = {}
        try:
            validator_class = self.validator_class
        except ValidationError as exc:
            raise ValidationError({"validator": exc}) from exc

        try:
            validator_class.check_params(self.params or {})
        except ValidationError as exc:
            errors["params"] = exc

        overrides = self.message_overrides or {}
        if not isinstance(overrides, dict):
            errors["message_overrides"] = _("Message overrides must be an object.")
        else:
            unknown = sorted(set(overrides) - validator_class.error_keys())
            if unknown:
                errors["message_overrides"] = _(
                    "%(validator)s does not declare the error keys: %(keys)s."
                ) % {"validator": self.validator, "keys": ", ".join(unknown)}
            elif any(not isinstance(message, str) for message in overrides.values()):
                errors["message_overrides"] = _("Every override must be a string.")

        if self.question_id is not None and not validator_class.supports_question_type(
            self.question.question_type
        ):
            errors["validator"] = _("%(validator)s does not support %(type)s questions.") % {
                "validator": self.validator,
                "type": self.question.get_question_type_display(),
            }

        if errors:
            raise ValidationError(errors)
