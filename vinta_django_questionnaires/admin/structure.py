"""One page that edits a whole questionnaire version.

The admin's own shape is one model per screen, and a questionnaire is four
models deep: to change a question's wording you open the questionnaire, then
the version, then the page, then the section, then the question.  Five loads
and four saves to fix a typo, and no way to see two questions at once.

So this is a single form over the whole tree.  Every page, section, question,
choice and validator of a version is on screen and posts together, which means
a reshuffle that touches six of them is one save and one acknowledgement rather
than six of each.

The one thing it cannot do in a single pass is fill in something that does not
exist yet: a brand-new page has no rows to hang a section off until it has been
saved.  Adding is therefore one save behind editing, which is a fair trade for
never having to leave the page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.db import transaction
from django.forms.models import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.editing import acknowledged_edit
from vinta_django_questionnaires.models import (
    Page,
    Question,
    QuestionChoice,
    QuestionnaireVersion,
    QuestionValidator,
    Section,
)
from vinta_django_questionnaires.validators import registry

if TYPE_CHECKING:
    from collections.abc import Iterator

#: How many blank rows each list offers. One is enough to add without clutter.
EXTRA = 1


class CompactForm(forms.ModelForm):
    """A model form whose widgets fit in a row rather than a page."""

    #: Rendered on the row itself; everything else hides behind a disclosure.
    summary_fields: tuple[str, ...] = ()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Textarea):
                # Not `setdefault`: Textarea ships with rows=10, and ten rows
                # per description is what makes a page of questions a mile long.
                widget.attrs["rows"] = 2
            if isinstance(widget, (forms.TextInput, forms.Textarea)):
                widget.attrs.setdefault("class", "vqa-input")
            if name == "order":
                widget.attrs.setdefault("class", "vqa-order")

    def summary(self) -> Iterator[Any]:
        for name in self.summary_fields:
            if name in self.fields:
                yield self[name]

    def rest(self) -> Iterator[Any]:
        """The visible fields that are not on the row.

        The primary key and the foreign key back to the parent are hidden
        fields the formset adds and needs posted back; they go out with
        `hidden_fields`, not as labelled inputs someone has to look at.
        """
        summary = set(self.summary_fields)
        for name in self.fields:
            if name in summary or name == "DELETE":
                continue
            field = self[name]
            if not field.is_hidden:
                yield field

    @property
    def is_new(self) -> bool:
        return self.instance.pk is None


class PageForm(CompactForm):
    summary_fields = ("order", "key", "title")

    class Meta:
        model = Page
        fields = (
            "order",
            "key",
            "title",
            "description",
            "conclusion",
            "condition",
            "is_skippable",
        )


class SectionForm(CompactForm):
    summary_fields = ("order", "key", "title")

    class Meta:
        model = Section
        fields = (
            "order",
            "key",
            "title",
            "description",
            "conclusion",
            "condition",
            "default_state",
        )


class QuestionForm(CompactForm):
    summary_fields = ("order", "key", "title", "question_type")

    class Meta:
        model = Question
        fields = (
            "order",
            "key",
            "title",
            "question_type",
            "description",
            "condition",
            "widget",
            "widget_props",
            "value_set",
            "item_question_type",
            "allows_other",
            "other_label",
            "sub_questionnaire",
            "sub_questionnaire_version",
            "requires_being_first_in_a_row",
            "requires_being_last_in_a_row",
        )


class ChoiceForm(CompactForm):
    summary_fields = ("order", "axis", "value", "label", "is_active")

    class Meta:
        model = QuestionChoice
        fields = ("order", "axis", "value", "label", "is_active", "extra")


class ValidatorForm(CompactForm):
    summary_fields = ("order", "validator", "is_enabled")
    validator = forms.ChoiceField(label=_("validator"), choices=[])

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Filled per instance, not at import: another app's validators are
        # registered by its app config, which has not run when this module is
        # first imported.
        field = self.fields["validator"]
        assert isinstance(field, forms.ChoiceField)
        field.choices = [("", "---------"), *registry.choices()]

    class Meta:
        model = QuestionValidator
        fields = ("order", "validator", "is_enabled", "params", "message_overrides")


def _factory(parent: Any, child: Any, form: Any) -> Any:
    return inlineformset_factory(parent, child, form=form, extra=EXTRA, can_delete=True)


PageFormSet = _factory(QuestionnaireVersion, Page, PageForm)
SectionFormSet = _factory(Page, Section, SectionForm)
QuestionFormSet = _factory(Section, Question, QuestionForm)
ChoiceFormSet = _factory(Question, QuestionChoice, ChoiceForm)
ValidatorFormSet = _factory(Question, QuestionValidator, ValidatorForm)


class AcknowledgementForm(forms.Form):
    """The one box for the whole page, rather than one per row."""

    understood = forms.BooleanField(
        required=False,
        label=_("I understand this changes what existing responses mean"),
    )
    edit_reason = forms.CharField(
        required=False,
        label=_("Reason"),
        widget=forms.TextInput(attrs={"size": 60}),
        help_text=_("Kept with the record of every change this save makes."),
    )


class QuestionNode:
    """A question, with the two lists that hang off it."""

    def __init__(self, form: Any, choices: Any, validators: Any) -> None:
        self.form = form
        self.choices = choices
        self.validators = validators

    @property
    def summary_count(self) -> str:
        """What is inside, for the closed row: a reason to open it or not."""
        parts = []
        choices = sum(1 for form in self.choices.forms if form.instance.pk)
        validators = sum(1 for form in self.validators.forms if form.instance.pk)
        if choices:
            parts.append(_("%(count)s choices") % {"count": choices})
        if validators:
            parts.append(_("%(count)s validators") % {"count": validators})
        return ", ".join(str(part) for part in parts)


class SectionNode:
    def __init__(self, form: Any, questions: Any, nodes: list[QuestionNode]) -> None:
        self.form = form
        self.questions = questions
        self.nodes = nodes

    @property
    def summary_count(self) -> str:
        count = len(self.nodes)
        return str(_("%(count)s questions") % {"count": count}) if count else str(_("empty"))


class PageNode:
    def __init__(self, form: Any, sections: Any, nodes: list[SectionNode]) -> None:
        self.form = form
        self.sections = sections
        self.nodes = nodes

    @property
    def summary_count(self) -> str:
        sections = len(self.nodes)
        questions = sum(len(section.nodes) for section in self.nodes)
        if not sections:
            return str(_("empty"))
        return str(
            _("%(sections)s sections, %(questions)s questions")
            % {"sections": sections, "questions": questions}
        )


class StructureEditor:
    """Every formset of one version, built, validated and saved together.

    Nesting is by primary key: a section's formset is prefixed with the page it
    belongs to, so the whole tree round-trips through one POST without the
    prefixes colliding.
    """

    def __init__(self, version: QuestionnaireVersion, data: Any = None) -> None:
        self.version = version
        self.data = data
        self.acknowledgement = AcknowledgementForm(data or None)
        self.pages = PageFormSet(data, instance=version, prefix="pages")
        self.nodes: list[PageNode] = []
        self._children: list[Any] = []
        #: Whether the formsets have been validated. Reading `formset.errors`
        #: validates on the spot, and doing that outside the acknowledgement
        #: context would report a gate the person is already being asked about.
        self._validated = False
        self._build()

    # -- building ----------------------------------------------------------
    def _build(self) -> None:
        for page in self.version.pages.all():
            sections = SectionFormSet(self.data, instance=page, prefix=f"sections-{page.pk}")
            self._children.append(sections)
            section_nodes = []
            for section in page.sections.all():
                questions = QuestionFormSet(
                    self.data, instance=section, prefix=f"questions-{section.pk}"
                )
                self._children.append(questions)
                question_nodes = []
                for question in section.questions.all():
                    choices = ChoiceFormSet(
                        self.data, instance=question, prefix=f"choices-{question.pk}"
                    )
                    validators = ValidatorFormSet(
                        self.data, instance=question, prefix=f"validators-{question.pk}"
                    )
                    self._children.extend([choices, validators])
                    question_nodes.append(
                        QuestionNode(
                            form=self._form_for(questions, question),
                            choices=choices,
                            validators=validators,
                        )
                    )
                section_nodes.append(
                    SectionNode(
                        form=self._form_for(sections, section),
                        questions=questions,
                        nodes=question_nodes,
                    )
                )
            self.nodes.append(
                PageNode(
                    form=self._form_for(self.pages, page),
                    sections=sections,
                    nodes=section_nodes,
                )
            )

    @staticmethod
    def _form_for(formset: Any, instance: Any) -> Any:
        """The form in *formset* that is editing *instance*."""
        for form in formset.forms:
            if form.instance.pk == instance.pk:
                return form
        return None  # pragma: no cover -- the formset is built from the same queryset

    # -- new rows ----------------------------------------------------------
    def new_page_forms(self) -> list[Any]:
        return [form for form in self.pages.forms if form.instance.pk is None]

    @staticmethod
    def new_forms(formset: Any) -> list[Any]:
        return [form for form in formset.forms if form.instance.pk is None]

    # -- saving ------------------------------------------------------------
    @property
    def formsets(self) -> list[Any]:
        return [self.pages, *self._children]

    def requires_acknowledgement(self) -> bool:
        return self.version.responses.exists()

    def is_valid(self, user: Any = None) -> bool:
        """Validate everything, with the acknowledgement in force while it runs.

        The models gate an unacknowledged edit in `clean()`, so the box has to
        be ticked before validation rather than before saving -- otherwise the
        whole page fails with a message about something the person already did.
        """
        if not self.acknowledgement.is_valid():
            return False
        if self.requires_acknowledgement() and not self.acknowledged:
            self.acknowledgement.add_error(
                "understood",
                _(
                    "This version already has responses. Tick the box to record that you mean "
                    "to change what they mean, or fork it into a new draft instead."
                ),
            )
            return False
        with self._in_force(user):
            # Every formset is validated, not just up to the first bad one, so
            # one page shows everything that needs fixing rather than the first
            # thing -- hence the list, which `all` would otherwise short-circuit.
            outcomes = [formset.is_valid() for formset in self.formsets]
            self._validated = True
            return all(outcomes)

    @property
    def acknowledged(self) -> bool:
        if not self.acknowledgement.is_bound:
            return False
        return bool(self.acknowledgement.cleaned_data.get("understood"))

    @property
    def reason(self) -> str:
        if not self.acknowledgement.is_bound:
            return ""
        return str(self.acknowledgement.cleaned_data.get("edit_reason", ""))

    def _in_force(self, user: Any) -> Any:
        return acknowledged_edit(user=user, reason=self.reason, understood=self.acknowledged)

    @transaction.atomic
    def save(self, user: Any = None) -> None:
        """Write it all, deepest first.

        A page being deleted takes its sections and questions with it, so the
        children go first: saving a question and then dropping the page it was
        on is harmless, and the other order is not.
        """
        with self._in_force(user):
            for formset in reversed(self._children):
                formset.save()
            self.pages.save()

    @property
    def field_count(self) -> int:
        """Roughly how many inputs this page posts.

        Everything on one form means one POST with everything in it, and
        Django caps that at ``DATA_UPLOAD_MAX_NUMBER_FIELDS`` -- 1000 by
        default, which a questionnaire of a dozen questions goes past. The
        count is what turns that from a 500 into a sentence saying what to set.
        """
        forms = sum(len(formset.forms) for formset in self.formsets)
        fields = sum(len(form.fields) for formset in self.formsets for form in formset.forms)
        # Four hidden inputs per management form, plus the id and fk per form.
        return fields + len(self.formsets) * 4 + forms * 2

    def errors(self) -> list[str]:
        """Everything wrong, flattened, for the note at the top of the page.

        Only reads the formsets once they have actually been validated: asking
        a bound formset for its errors validates it there and then, and doing
        that here would run the acknowledgement gate a second time, outside the
        context that satisfies it, and report a problem nobody has yet had the
        chance to fix.
        """
        found = [
            str(message)
            for messages in self.acknowledgement.errors.values()
            for message in messages
        ]
        if not self._validated:
            return found
        for formset in self.formsets:
            found.extend(str(error) for error in formset.non_form_errors())
            for form in formset.forms:
                for field, messages in form.errors.items():
                    label = form.fields[field].label if field in form.fields else ""
                    found.extend(
                        f"{label}: {message}" if label else str(message) for message in messages
                    )
        return found


__all__ = [
    "AcknowledgementForm",
    "ChoiceForm",
    "PageForm",
    "QuestionForm",
    "SectionForm",
    "StructureEditor",
    "ValidatorForm",
]
