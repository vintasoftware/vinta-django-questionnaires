"""Exercises the questionnaire definition models."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from tests.conftest import make_question
from vinta_django_questionnaires.filters import compile_filter_expression
from vinta_django_questionnaires.models import (
    DEFAULT_COLUMN_COUNT,
    LayerColumns,
    Page,
    QuestionChoice,
    QuestionMinimumColumns,
    Questionnaire,
    QuestionnaireVersion,
    QuestionnaireWidget,
    QuestionValidator,
    Section,
    WidgetQuestionType,
    WindowSizeRange,
)
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.validators import BaseValidator, ValidatorOutput, registry


class TestLayout:
    def test_columns_fall_back_to_the_default(self, ranges, section):
        assert section.resolve_columns(ranges["desktop"]) == DEFAULT_COLUMN_COUNT

    def test_a_layer_inherits_from_its_parents(self, version, ranges, section):
        LayerColumns.objects.create(
            questionnaire_version=version, window_size_range=ranges["desktop"], columns=8
        )
        assert section.resolve_columns(ranges["desktop"]) == 8

        LayerColumns.objects.create(
            page=section.page, window_size_range=ranges["desktop"], columns=6
        )
        assert section.resolve_columns(ranges["desktop"]) == 6

        LayerColumns.objects.create(
            section=section, window_size_range=ranges["desktop"], columns=4
        )
        assert section.resolve_columns(ranges["desktop"]) == 4
        assert section.page.resolve_columns(ranges["desktop"]) == 6

    def test_inheritance_is_per_range(self, version, ranges, section):
        LayerColumns.objects.create(
            questionnaire_version=version, window_size_range=ranges["mobile"], columns=4
        )
        assert section.column_layout() == {"mobile": 4, "desktop": DEFAULT_COLUMN_COUNT}

    def test_columns_belong_to_exactly_one_layer(self, version, ranges, section):
        columns = LayerColumns(
            questionnaire_version=version,
            page=section.page,
            window_size_range=ranges["desktop"],
            columns=4,
        )
        with pytest.raises(ValidationError, match="exactly one"):
            columns.save()

    def test_a_question_asks_for_a_minimum_width(self, ranges, section):
        question = make_question(section)
        assert question.resolve_minimum_columns(ranges["mobile"]) == DEFAULT_COLUMN_COUNT

        QuestionMinimumColumns.objects.create(
            question=question, window_size_range=ranges["desktop"], minimum_columns=3
        )
        assert question.minimum_column_layout() == {"mobile": DEFAULT_COLUMN_COUNT, "desktop": 3}

    def test_ranges_may_not_overlap(self, version, ranges):
        overlapping = WindowSizeRange(
            questionnaire_version=version, key="tablet", min_width=700, max_width=900
        )
        with pytest.raises(ValidationError, match="overlaps"):
            overlapping.save()


class TestKeys:
    def test_section_keys_are_unique_within_a_page(self, section):
        with pytest.raises((ValidationError, IntegrityError)):
            Section.objects.create(page=section.page, key="basics", title="Basics again")

    def test_question_keys_are_unique_within_a_version(self, version, section):
        make_question(section)
        other_page = Page.objects.create(questionnaire_version=version, key="more", title="More")
        other_section = Section.objects.create(page=other_page, key="basics", title="Basics")
        with pytest.raises(ValidationError, match="already uses this key"):
            make_question(other_section)


class TestConditions:
    def test_a_bad_condition_is_rejected_on_save(self, section):
        with pytest.raises(ValidationError, match="JMESPath"):
            make_question(section, condition="not a [valid expression")

    def test_conditions_select_what_gets_validated(self, version, section):
        section.page.condition = "role == 'admin'"
        section.page.save()
        make_question(section, key="name")
        make_question(section, key="badge", condition="has_badge", order=1)

        assert [question.key for question in version.iter_applicable_questions({})] == []
        applicable = version.iter_applicable_questions({"role": "admin", "has_badge": True})
        assert [question.key for question in applicable] == ["name", "badge"]

        applicable = version.iter_applicable_questions({"role": "admin"})
        assert [question.key for question in applicable] == ["name"]


class TestWidgets:
    @pytest.fixture
    def widget(self, db):
        widget = QuestionnaireWidget.objects.create(
            key="text-input",
            name="Text input",
            props_schema={
                "type": "object",
                "properties": {"placeholder": {"type": "string"}},
                "additionalProperties": False,
            },
            default_props={"placeholder": "Type here"},
        )
        WidgetQuestionType.objects.create(
            widget=widget, question_type=QuestionType.FREE_TEXT, is_default=True
        )
        return widget

    def test_a_question_falls_back_to_the_type_default(self, widget, section):
        question = make_question(section)
        assert question.resolved_widget == widget
        assert question.resolved_widget_props == {"placeholder": "Type here"}

    def test_props_are_checked_against_the_schema(self, widget, section):
        with pytest.raises(ValidationError, match="placeholder"):
            make_question(section, widget=widget, widget_props={"placeholder": 42})

    def test_props_override_the_widget_defaults(self, widget, section):
        question = make_question(section, widget_props={"placeholder": "Full name"})
        assert question.resolved_widget_props == {"placeholder": "Full name"}

    def test_a_widget_only_renders_the_types_it_supports(self, widget, section):
        with pytest.raises(ValidationError, match="does not support"):
            make_question(section, question_type=QuestionType.NUMBER, widget=widget)

    def test_the_props_schema_must_be_a_schema(self, db):
        with pytest.raises(ValidationError, match="Invalid JSON Schema"):
            QuestionnaireWidget.objects.create(
                key="broken", name="Broken", props_schema={"type": "nonsense"}
            )


class TestQuestionTypeRules:
    def test_free_text_takes_no_choices(self, section):
        question = make_question(section)
        with pytest.raises(ValidationError, match="do not take choices"):
            QuestionChoice.objects.create(question=question, value="a", label="A")

    def test_a_matrix_takes_rows_and_columns(self, section):
        question = make_question(section, question_type=QuestionType.BINARY_MATRIX)
        with pytest.raises(ValidationError, match="rows and columns only"):
            QuestionChoice.objects.create(question=question, value="a", label="A")
        QuestionChoice.objects.create(question=question, axis="row", value="a", label="A")

    def test_a_select_needs_a_value_set(self, section):
        with pytest.raises(ValidationError, match="need a value set"):
            make_question(section, question_type=QuestionType.SINGLE_SELECT)

    def test_only_choice_questions_take_an_other_option(self, section):
        with pytest.raises(ValidationError, match="other option"):
            make_question(section, question_type=QuestionType.NUMBER, allows_other=True)
        make_question(
            section, key="colour", question_type=QuestionType.SINGLE_CHOICE, allows_other=True
        )

    def test_a_list_of_items_needs_an_item_type(self, section):
        with pytest.raises(ValidationError, match="type of its items"):
            make_question(section, question_type=QuestionType.ITEM_LIST)
        with pytest.raises(ValidationError, match="single-value type"):
            make_question(
                section,
                question_type=QuestionType.ITEM_LIST,
                item_question_type=QuestionType.MULTIPLE_FILES,
            )
        make_question(
            section,
            question_type=QuestionType.ITEM_LIST,
            item_question_type=QuestionType.NUMBER,
        )


class TestNesting:
    def test_a_sub_questionnaire_question_needs_a_target(self, section):
        with pytest.raises(ValidationError, match="needs a sub-questionnaire"):
            make_question(section, question_type=QuestionType.SUB_QUESTIONNAIRE)

    def test_a_questionnaire_may_not_nest_itself(self, version, section):
        with pytest.raises(ValidationError, match="loop back"):
            make_question(
                section,
                question_type=QuestionType.SUB_QUESTIONNAIRE,
                sub_questionnaire=version.questionnaire,
            )

    def test_indirect_cycles_are_caught(self, version, section):
        other = Questionnaire.objects.create(key="address")
        other_version = QuestionnaireVersion.objects.create(
            questionnaire=other, version=1, title="Address"
        )
        other_page = Page.objects.create(
            questionnaire_version=other_version, key="p", title="Page"
        )
        other_section = Section.objects.create(page=other_page, key="s", title="Section")
        make_question(
            other_section,
            key="back",
            question_type=QuestionType.SUB_QUESTIONNAIRE,
            sub_questionnaire=version.questionnaire,
        )
        with pytest.raises(ValidationError, match="loop back"):
            make_question(
                section,
                key="address",
                question_type=QuestionType.SUB_QUESTIONNAIRE_LIST,
                sub_questionnaire=other,
            )

    def test_a_pinned_version_must_belong_to_the_target(self, version, section):
        other = Questionnaire.objects.create(key="address")
        QuestionnaireVersion.objects.create(questionnaire=other, version=1, title="Address")
        with pytest.raises(ValidationError, match="different questionnaire"):
            make_question(
                section,
                question_type=QuestionType.SUB_QUESTIONNAIRE,
                sub_questionnaire=other,
                sub_questionnaire_version=version,
            )


class TestValidatorChain:
    @pytest.fixture
    def registered(self):
        class MinLength(BaseValidator):
            key = "test_min_length"
            error_messages = {"too_short": "Use at least {minimum} characters."}
            params_schema = {
                "type": "object",
                "properties": {"minimum": {"type": "integer"}},
                "required": ["minimum"],
                "additionalProperties": False,
            }

            def validate(self, value, context):
                if len(value) < self.params["minimum"]:
                    self.fail("too_short", minimum=self.params["minimum"])
                return ValidatorOutput(value=value, data={"length": len(value)})

        class Trimmed(BaseValidator):
            key = "test_trimmed"
            error_messages = {"padded": "Remove the surrounding spaces."}

            def validate(self, value, context):
                # What the previous link recorded is available here.
                assert context.data_for("test_min_length") == {"length": len(value)}
                if value != value.strip():
                    self.fail("padded")
                return

        registry.register(MinLength, force=True)
        registry.register(Trimmed, force=True)
        yield
        registry.unregister("test_min_length")
        registry.unregister("test_trimmed")

    def test_the_chain_runs_in_order_and_shares_a_context(self, registered, section):
        question = make_question(section)
        QuestionValidator.objects.create(
            question=question, validator="test_min_length", order=0, params={"minimum": 3}
        )
        QuestionValidator.objects.create(question=question, validator="test_trimmed", order=1)

        context = question.run_validators("Hugo ")
        assert [outcome.validator for outcome in context.outcomes] == [
            "test_min_length",
            "test_trimmed",
        ]
        assert [issue.error_key for issue in context.issues] == ["padded"]

    def test_messages_can_be_overridden_per_error_key(self, registered, section):
        question = make_question(section)
        QuestionValidator.objects.create(
            question=question,
            validator="test_min_length",
            params={"minimum": 5},
            message_overrides={"too_short": "Name too short ({minimum} min)."},
        )
        context = question.run_validators("ab")
        assert context.issues[0].message == "Name too short (5 min)."

    def test_unknown_validators_are_rejected(self, section):
        question = make_question(section)
        with pytest.raises(ValidationError, match="no validator registered"):
            QuestionValidator.objects.create(question=question, validator="nope")

    def test_params_are_checked_against_the_validator_schema(self, registered, section):
        question = make_question(section)
        with pytest.raises(ValidationError, match="minimum"):
            QuestionValidator.objects.create(
                question=question, validator="test_min_length", params={}
            )

    def test_overrides_must_name_a_declared_error_key(self, registered, section):
        question = make_question(section)
        with pytest.raises(ValidationError, match="does not declare"):
            QuestionValidator.objects.create(
                question=question,
                validator="test_min_length",
                params={"minimum": 1},
                message_overrides={"typo": "..."},
            )


class TestFilterDSL:
    def test_it_compiles_to_a_queryset_filter(self):
        query = compile_filter_expression('status = "active" and not slug in ["a", "b"]')
        assert str(query) == str(
            compile_filter_expression('status = "active"')
            & ~compile_filter_expression('slug in ["a", "b"]')
        )
