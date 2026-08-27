"""The validation plan handed to the client."""

from __future__ import annotations

import pytest

from tests.conftest import make_question
from vinta_django_questionnaires.models import (
    LayerColumns,
    Page,
    QuestionChoice,
    QuestionMinimumColumns,
    Questionnaire,
    QuestionnaireVersion,
    QuestionnaireWidget,
    QuestionValidator,
    Section,
    ValueSet,
    WidgetQuestionType,
)
from vinta_django_questionnaires.plan import (
    MAX_NESTING_DEPTH,
    PLAN_VERSION,
    question_plan,
    questionnaire_plan,
)
from vinta_django_questionnaires.question_types import QuestionType


@pytest.fixture
def question(section):
    return make_question(section, condition="role == 'staff'")


class TestQuestionPlan:
    def test_it_carries_the_type_and_the_condition(self, question):
        plan = question_plan(question)

        assert plan["key"] == "name"
        assert plan["type"] == QuestionType.FREE_TEXT
        assert plan["condition"] == "role == 'staff'"

    def test_checks_arrive_in_the_order_they_run(self, question):
        QuestionValidator.objects.create(
            question=question, validator="max_length", order=1, params={"maximum": 10}
        )
        QuestionValidator.objects.create(
            question=question, validator="min_length", order=0, params={"minimum": 2}
        )

        kinds = [check["kind"] for check in question_plan(question)["checks"]]

        assert kinds == ["string.min", "string.max"]

    def test_a_check_carries_its_resolved_message(self, question):
        QuestionValidator.objects.create(
            question=question,
            validator="min_length",
            params={"minimum": 2},
            message_overrides={"too_short": "At least {minimum}, please."},
        )

        check = question_plan(question)["checks"][0]

        assert check["message"] == "At least {minimum}, please."
        assert check["params"] == {"minimum": 2}
        assert check["validator"] == "min_length"
        assert check["skipWhenEmpty"] is True

    def test_a_disabled_validator_is_left_out(self, question):
        QuestionValidator.objects.create(
            question=question, validator="min_length", params={"minimum": 2}, is_enabled=False
        )

        assert question_plan(question)["checks"] == []

    def test_a_predicate_marks_the_chain_as_context_reading(self, question):
        QuestionValidator.objects.create(
            question=question, validator="jmespath_predicate", params={"expression": "value"}
        )

        assert question_plan(question)["usesContext"] is True

    def test_choices_travel_with_a_choice_question(self, section):
        question = make_question(
            section, key="colour", question_type=QuestionType.SINGLE_CHOICE, allows_other=True
        )
        QuestionChoice.objects.create(question=question, value="red", label="Red")

        plan = question_plan(question)

        assert plan["choices"] == [{"value": "red", "label": "Red"}]
        assert plan["allowsOther"] is True

    def test_a_matrix_travels_with_both_axes(self, section):
        question = make_question(section, key="grid", question_type=QuestionType.BINARY_MATRIX)
        QuestionChoice.objects.create(question=question, axis="row", value="mon", label="Monday")
        QuestionChoice.objects.create(
            question=question, axis="column", value="am", label="Morning"
        )

        plan = question_plan(question)

        assert plan["matrix"] == {
            "rows": [{"value": "mon", "label": "Monday"}],
            "columns": [{"value": "am", "label": "Morning"}],
        }

    def test_a_value_set_is_referenced_not_inlined(self, section):
        value_set = ValueSet.objects.create(key="countries", name="Countries")
        question = make_question(
            section, key="country", question_type=QuestionType.SINGLE_SELECT, value_set=value_set
        )

        assert question_plan(question)["valueSet"] == {
            "key": "countries",
            "source": "static",
            "resolvedByTheClient": False,
        }


class TestLayoutTravelsWithThePlan:
    def test_a_version_carries_its_breakpoints_and_columns(self, version, ranges, section):
        LayerColumns.objects.create(
            questionnaire_version=version, window_size_range=ranges["desktop"], columns=8
        )

        plan = questionnaire_plan(version)

        assert [entry["key"] for entry in plan["windowSizeRanges"]] == ["mobile", "desktop"]
        assert plan["windowSizeRanges"][0]["maxWidth"] == 767
        assert plan["columns"] == {"mobile": 12, "desktop": 8}

    def test_each_layer_reports_what_it_resolved_to(self, version, ranges, section):
        LayerColumns.objects.create(
            questionnaire_version=version, window_size_range=ranges["desktop"], columns=8
        )
        LayerColumns.objects.create(
            section=section, window_size_range=ranges["desktop"], columns=6
        )
        make_question(section)

        page_plan = questionnaire_plan(version)["pages"][0]

        assert page_plan["columns"] == {"mobile": 12, "desktop": 8}
        assert page_plan["sections"][0]["columns"] == {"mobile": 12, "desktop": 6}

    def test_a_question_carries_what_it_needs_to_be_placed(self, version, ranges, section):
        question = make_question(section)
        QuestionMinimumColumns.objects.create(
            question=question, window_size_range=ranges["desktop"], minimum_columns=4
        )
        question.requires_being_first_in_a_row = True
        question.save()

        plan = question_plan(question)

        assert plan["minimumColumns"] == {"mobile": 12, "desktop": 4}
        assert plan["requiresBeingFirstInARow"] is True
        assert plan["requiresBeingLastInARow"] is False

    def test_a_question_carries_the_widget_it_resolved_to(self, section):
        widget = QuestionnaireWidget.objects.create(
            key="text-input",
            name="Text input",
            props_schema={"type": "object", "properties": {"placeholder": {"type": "string"}}},
            default_props={"placeholder": "Type here"},
        )
        WidgetQuestionType.objects.create(
            widget=widget, question_type=QuestionType.FREE_TEXT, is_default=True
        )
        question = make_question(section)

        plan = question_plan(question)

        assert plan["widget"] == "text-input"
        assert plan["widgetProps"] == {"placeholder": "Type here"}


class TestQuestionnairePlan:
    def test_it_mirrors_the_tree(self, version, section):
        make_question(section)

        plan = questionnaire_plan(version)

        assert plan["planVersion"] == PLAN_VERSION
        assert plan["questionnaire"] == "intake"
        assert [page["key"] for page in plan["pages"]] == ["about"]
        assert [s["key"] for s in plan["pages"][0]["sections"]] == ["basics"]
        assert [q["key"] for q in plan["pages"][0]["sections"][0]["questions"]] == ["name"]

    def test_conditions_travel_at_every_level(self, version, section):
        section.page.condition = "role == 'staff'"
        section.page.save()
        section.condition = "wants_details"
        section.save()
        make_question(section, condition="has_badge")

        page_plan = questionnaire_plan(version)["pages"][0]

        assert page_plan["condition"] == "role == 'staff'"
        assert page_plan["sections"][0]["condition"] == "wants_details"
        assert page_plan["sections"][0]["questions"][0]["condition"] == "has_badge"

    def test_a_sub_questionnaire_is_expanded(self, version, section):
        address = _questionnaire("address", "Address")
        make_question(
            section,
            key="address",
            question_type=QuestionType.SUB_QUESTIONNAIRE,
            sub_questionnaire=address.questionnaire,
            sub_questionnaire_version=address,
        )

        sub = questionnaire_plan(version)["pages"][0]["sections"][0]["questions"][0]

        assert sub["subQuestionnaire"]["questionnaire"] == "address"
        assert [
            q["key"] for q in sub["subQuestionnaire"]["pages"][0]["sections"][0]["questions"]
        ] == ["line_1"]

    def test_nesting_past_the_limit_is_referenced_instead(self, version, section):
        address = _questionnaire("address", "Address")
        make_question(
            section,
            key="address",
            question_type=QuestionType.SUB_QUESTIONNAIRE,
            sub_questionnaire=address.questionnaire,
            sub_questionnaire_version=address,
        )

        plan = questionnaire_plan(version, depth=MAX_NESTING_DEPTH)
        sub = plan["pages"][0]["sections"][0]["questions"][0]["subQuestionnaire"]

        assert sub == {"ref": {"questionnaire": "address", "version": 1}}


def _questionnaire(key, title):
    questionnaire = Questionnaire.objects.create(key=key)
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title=title
    )
    page = Page.objects.create(questionnaire_version=version, key="p", title="Page")
    section = Section.objects.create(page=page, key="s", title="Section")
    make_question(section, key="line_1", title="Line 1")
    return version
