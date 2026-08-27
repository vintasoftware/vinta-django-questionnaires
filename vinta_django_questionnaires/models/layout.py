"""The responsive grid: window size ranges, and the columns each layer sets.

A questionnaire declares the window size ranges it supports.  Every layer --
the questionnaire version, a page, a section -- may then say how many columns
its grid has in each of those ranges.  A layer that says nothing inherits from
its parent; when nobody says anything the grid has
``DEFAULT_COLUMN_COUNT`` columns.  Questions work the other way around: they
declare the *minimum* number of columns they need per range.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.models.base import BaseModel

if TYPE_CHECKING:
    from vinta_django_questionnaires.models.questionnaires import QuestionnaireVersion

#: The column count assumed when no layer defines one.
DEFAULT_COLUMN_COUNT = 12


class WindowSizeRange(BaseModel):
    """One breakpoint of a questionnaire, as a half-open range of widths."""

    questionnaire_version = models.ForeignKey(
        "vinta_django_questionnaires.QuestionnaireVersion",
        on_delete=models.CASCADE,
        related_name="window_size_ranges",
        verbose_name=_("questionnaire version"),
    )
    key = models.SlugField(_("key"), max_length=50)
    label = models.CharField(_("label"), max_length=100, blank=True, default="")
    min_width = models.PositiveIntegerField(
        _("minimum width"), default=0, help_text=_("In pixels, inclusive.")
    )
    max_width = models.PositiveIntegerField(
        _("maximum width"),
        null=True,
        blank=True,
        help_text=_("In pixels, inclusive. Leave empty for an unbounded range."),
    )
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("window size range")
        verbose_name_plural = _("window size ranges")
        ordering = ["questionnaire_version", "order", "min_width"]
        constraints = [
            models.UniqueConstraint(
                fields=["questionnaire_version", "key"],
                name="unique_window_size_range_key_per_version",
            ),
            models.CheckConstraint(
                condition=Q(max_width__isnull=True) | Q(max_width__gt=F("min_width")),
                name="window_size_range_max_width_above_min_width",
            ),
        ]

    def __str__(self) -> str:
        upper = self.max_width if self.max_width is not None else "∞"
        return f"{self.key} ({self.min_width}-{upper})"

    def clean(self) -> None:
        super().clean()
        if self.max_width is not None and self.max_width <= self.min_width:
            raise ValidationError(
                {"max_width": _("The maximum width must be greater than the minimum width.")}
            )
        if not self.questionnaire_version_id:
            return
        siblings = WindowSizeRange.objects.filter(
            questionnaire_version_id=self.questionnaire_version_id
        ).exclude(pk=self.pk)
        for sibling in siblings:
            if self._overlaps(sibling):
                raise ValidationError(
                    _("This range overlaps %(other)s."),
                    code="overlapping_range",
                    params={"other": str(sibling)},
                )

    def _overlaps(self, other: WindowSizeRange) -> bool:
        own_max = self.max_width if self.max_width is not None else float("inf")
        other_max = other.max_width if other.max_width is not None else float("inf")
        return self.min_width <= other_max and other.min_width <= own_max

    def matches(self, width: int) -> bool:
        """Whether a viewport *width* falls in this range."""
        return self.min_width <= width and (self.max_width is None or width <= self.max_width)


class LayerMixin(models.Model):
    """Shared by the three layers that can define a column count.

    Subclasses set ``layer_field`` to the name of the ``LayerColumns`` field
    that points back at them, and say who their parent layer is.
    """

    #: Name of the ``LayerColumns`` foreign key that points at this layer.
    layer_field: ClassVar[str] = ""

    class Meta:
        abstract = True

    def get_parent_layer(self) -> LayerMixin | None:
        """The layer this one inherits column counts from."""
        return None

    def get_questionnaire_version(self) -> QuestionnaireVersion:
        raise NotImplementedError

    def resolve_columns(self, window_size_range: WindowSizeRange) -> int:
        """The column count for *window_size_range*, walking up to the parents."""
        layer: LayerMixin | None = self
        while layer is not None:
            if layer.pk is not None and layer.layer_field:
                entry = LayerColumns.objects.filter(
                    window_size_range=window_size_range, **{layer.layer_field: layer}
                ).first()
                if entry is not None:
                    return entry.columns
            layer = layer.get_parent_layer()
        return DEFAULT_COLUMN_COUNT

    def column_layout(self) -> dict[str, int]:
        """The resolved column count of every range, keyed by range key."""
        ranges = self.get_questionnaire_version().window_size_ranges.all()
        return {
            window_size_range.key: self.resolve_columns(window_size_range)
            for window_size_range in ranges
        }


class LayerColumns(BaseModel):
    """How many columns one layer's grid has in one window size range.

    Exactly one of the three layer foreign keys is set; which one it is says
    which layer the row belongs to.
    """

    window_size_range = models.ForeignKey(
        WindowSizeRange,
        on_delete=models.CASCADE,
        related_name="layer_columns",
        verbose_name=_("window size range"),
    )
    columns = models.PositiveSmallIntegerField(
        _("columns"), default=DEFAULT_COLUMN_COUNT, validators=[MinValueValidator(1)]
    )
    questionnaire_version = models.ForeignKey(
        "vinta_django_questionnaires.QuestionnaireVersion",
        on_delete=models.CASCADE,
        related_name="layer_columns",
        null=True,
        blank=True,
        verbose_name=_("questionnaire version"),
    )
    page = models.ForeignKey(
        "vinta_django_questionnaires.Page",
        on_delete=models.CASCADE,
        related_name="layer_columns",
        null=True,
        blank=True,
        verbose_name=_("page"),
    )
    section = models.ForeignKey(
        "vinta_django_questionnaires.Section",
        on_delete=models.CASCADE,
        related_name="layer_columns",
        null=True,
        blank=True,
        verbose_name=_("section"),
    )

    class Meta:
        verbose_name = _("layer columns")
        verbose_name_plural = _("layer columns")
        constraints = [
            models.UniqueConstraint(
                fields=["questionnaire_version", "window_size_range"],
                name="unique_columns_per_version_and_range",
            ),
            models.UniqueConstraint(
                fields=["page", "window_size_range"],
                name="unique_columns_per_page_and_range",
            ),
            models.UniqueConstraint(
                fields=["section", "window_size_range"],
                name="unique_columns_per_section_and_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(questionnaire_version__isnull=False, page__isnull=True, section__isnull=True)
                    | Q(
                        questionnaire_version__isnull=True,
                        page__isnull=False,
                        section__isnull=True,
                    )
                    | Q(
                        questionnaire_version__isnull=True,
                        page__isnull=True,
                        section__isnull=False,
                    )
                ),
                name="layer_columns_belong_to_exactly_one_layer",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.layer or '?'} / {self.window_size_range_id}: {self.columns}"

    @property
    def layer(self) -> LayerMixin | None:
        """Whichever of the three layers this row belongs to."""
        return self.questionnaire_version or self.page or self.section

    def clean(self) -> None:
        super().clean()
        layers = [self.questionnaire_version_id, self.page_id, self.section_id]
        if sum(layer_id is not None for layer_id in layers) != 1:
            raise ValidationError(
                _("Set exactly one of questionnaire version, page or section."),
                code="ambiguous_layer",
            )
        layer = self.layer
        if layer is not None and self.window_size_range_id is not None:
            version = layer.get_questionnaire_version()
            if self.window_size_range.questionnaire_version_id != version.pk:
                raise ValidationError(
                    {
                        "window_size_range": _(
                            "This window size range belongs to another questionnaire version."
                        )
                    }
                )


class QuestionMinimumColumns(BaseModel):
    """The narrowest a question may be rendered in one window size range."""

    question = models.ForeignKey(
        "vinta_django_questionnaires.Question",
        on_delete=models.CASCADE,
        related_name="minimum_columns",
        verbose_name=_("question"),
    )
    window_size_range = models.ForeignKey(
        WindowSizeRange,
        on_delete=models.CASCADE,
        related_name="question_minimum_columns",
        verbose_name=_("window size range"),
    )
    minimum_columns = models.PositiveSmallIntegerField(
        _("minimum columns"), default=DEFAULT_COLUMN_COUNT, validators=[MinValueValidator(1)]
    )

    class Meta:
        verbose_name = _("question minimum columns")
        verbose_name_plural = _("question minimum columns")
        constraints = [
            models.UniqueConstraint(
                fields=["question", "window_size_range"],
                name="unique_minimum_columns_per_question_and_range",
            )
        ]

    def __str__(self) -> str:
        return f"{self.question_id} / {self.window_size_range_id}: {self.minimum_columns}"

    def clean(self) -> None:
        super().clean()
        if not self.question_id or not self.window_size_range_id:
            return
        version = self.question.get_questionnaire_version()
        if self.window_size_range.questionnaire_version_id != version.pk:
            raise ValidationError(
                {
                    "window_size_range": _(
                        "This window size range belongs to another questionnaire version."
                    )
                }
            )
