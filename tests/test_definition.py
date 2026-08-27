"""The editable document: reading one, writing one back, and refusing one."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model

from tests.conftest import make_question
from vinta_django_questionnaires.catalog import editor_catalog
from vinta_django_questionnaires.definition import (
    DefinitionError,
    apply_definition,
    definition_document,
)
from vinta_django_questionnaires.editing import Acknowledgement
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    LayerColumns,
    Page,
    Question,
    QuestionChoice,
    QuestionnaireResponse,
    QuestionValidator,
    Section,
)
from vinta_django_questionnaires.question_types import QuestionType


@pytest.fixture
def populated(version, ranges, section):
    """A version with layout, choices and a validator on it."""
    LayerColumns.objects.create(
        questionnaire_version=version, window_size_range=ranges["mobile"], columns=4
    )
    LayerColumns.objects.create(section=section, window_size_range=ranges["desktop"], columns=6)
    question = make_question(
        section,
        key="flavour",
        title="Favourite flavour",
        question_type=QuestionType.SINGLE_CHOICE,
    )
    QuestionChoice.objects.create(question=question, value="vanilla", label="Vanilla", order=0)
    QuestionChoice.objects.create(question=question, value="salt", label="Salted", order=1)
    QuestionValidator.objects.create(question=question, validator="required", order=0)
    return version


# ------------------------------------------------------------------ reading


def test_document_carries_the_whole_tree(populated):
    document = definition_document(populated)

    assert document["questionnaire"]["key"] == "intake"
    page = document["pages"][0]
    assert page["key"] == "about"
    question = page["sections"][0]["questions"][0]
    assert question["key"] == "flavour"
    assert [choice["value"] for choice in question["choices"]] == ["vanilla", "salt"]
    assert [binding["validator"] for binding in question["validators"]] == ["required"]


def test_document_carries_declared_columns_not_inherited_ones(populated):
    document = definition_document(populated)

    assert document["columns"] == {"mobile": 4}
    # The page declares nothing and says so, rather than repeating its parent.
    assert document["pages"][0]["columns"] == {}
    assert document["pages"][0]["sections"][0]["columns"] == {"desktop": 6}


def test_document_says_whether_an_edit_needs_acknowledging(populated):
    assert definition_document(populated)["state"]["requiresAcknowledgement"] is False

    QuestionnaireResponse.objects.create(questionnaire_version=populated)

    state = definition_document(populated)["state"]
    assert state["requiresAcknowledgement"] is True
    assert state["responseCount"] == 1


def test_document_is_json(populated):
    assert json.loads(json.dumps(definition_document(populated)))


# ------------------------------------------------------------------ writing


def test_applying_what_was_read_changes_nothing(populated):
    before = definition_document(populated)

    apply_definition(populated, before)

    assert definition_document(populated) == before


def test_editing_a_title_goes_through(populated):
    document = definition_document(populated)
    document["pages"][0]["title"] = "About your tastes"

    apply_definition(populated, document)

    assert Page.objects.get(key="about").title == "About your tastes"


def test_a_new_page_is_created_in_order(populated):
    document = definition_document(populated)
    document["pages"].insert(
        0,
        {
            "key": "intro",
            "title": "Welcome",
            "description": "",
            "conclusion": "",
            "condition": "",
            "isSkippable": True,
            "columns": {},
            "sections": [],
        },
    )

    apply_definition(populated, document)

    assert [page.key for page in populated.pages.all()] == ["intro", "about"]
    assert Page.objects.get(key="intro").is_skippable is True


def test_a_page_left_out_is_deleted(populated):
    document = definition_document(populated)
    document["pages"] = []

    apply_definition(populated, document)

    assert not populated.pages.exists()
    assert not Question.objects.filter(key="flavour").exists()


def test_choices_are_matched_by_value(populated):
    document = definition_document(populated)
    question = document["pages"][0]["sections"][0]["questions"][0]
    stored = QuestionChoice.objects.get(value="vanilla")
    question["choices"][0]["label"] = "Plain vanilla"
    question["choices"].pop()

    apply_definition(populated, document)

    assert QuestionChoice.objects.get(pk=stored.pk).label == "Plain vanilla"
    assert not QuestionChoice.objects.filter(value="salt").exists()


def test_dropping_choices_and_changing_the_type_in_one_go(populated):
    document = definition_document(populated)
    question = document["pages"][0]["sections"][0]["questions"][0]
    question["questionType"] = QuestionType.FREE_TEXT
    question["choices"] = []
    question["validators"] = []

    apply_definition(populated, document)

    assert Question.objects.get(key="flavour").question_type == QuestionType.FREE_TEXT
    assert not QuestionChoice.objects.exists()


def test_the_validator_chain_is_matched_by_position(populated):
    document = definition_document(populated)
    question = document["pages"][0]["sections"][0]["questions"][0]
    question["validators"].append(
        {
            "validator": "one_of",
            "params": {"values": ["vanilla", "salt"]},
            "messageOverrides": {},
            "isEnabled": True,
        }
    )

    apply_definition(populated, document)

    chain = QuestionValidator.objects.filter(question__key="flavour").order_by("order")
    assert [binding.validator for binding in chain] == ["required", "one_of"]
    assert [binding.order for binding in chain] == [0, 1]


def test_columns_can_be_added_and_removed(populated, ranges):
    document = definition_document(populated)
    document["columns"] = {"desktop": 12}
    document["pages"][0]["columns"] = {"mobile": 2}

    apply_definition(populated, document)

    assert definition_document(populated)["columns"] == {"desktop": 12}
    assert definition_document(populated)["pages"][0]["columns"] == {"mobile": 2}


def test_a_window_size_range_can_be_renamed_by_replacing_it(populated):
    document = definition_document(populated)
    document["windowSizeRanges"] = [
        {"key": "small", "label": "Small", "minWidth": 0, "maxWidth": 767},
        {"key": "desktop", "label": "", "minWidth": 768, "maxWidth": None},
    ]
    # The columns keyed by the range that went have to go with it.
    document["columns"] = {}

    apply_definition(populated, document)

    assert [entry["key"] for entry in definition_document(populated)["windowSizeRanges"]] == [
        "small",
        "desktop",
    ]


# ----------------------------------------------------------------- refusing


def test_a_document_that_does_not_hold_up_writes_nothing(populated):
    document = definition_document(populated)
    document["pages"][0]["title"] = "Changed"
    document["pages"][0]["sections"][0]["questions"][0]["questionType"] = "not_a_type"

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert raised.value.issues[0].path == "pages.0.sections.0.questions.0"
    assert "question_type" in raised.value.issues[0].errors
    assert Page.objects.get(key="about").title == "About you"


def test_every_bad_node_is_reported_at_once(populated):
    """One bad node does not hide the next one -- only its own children."""
    document = definition_document(populated)
    document["pages"][0]["condition"] = "!!! not jmespath"
    document["pages"].append(
        {
            "key": "extra",
            "title": "x" * 300,
            "description": "",
            "conclusion": "",
            "condition": "",
            "isSkippable": False,
            "columns": {},
            "sections": [],
        }
    )

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert {issue.path for issue in raised.value.issues} == {"pages.0", "pages.1"}


def test_a_node_that_will_not_go_takes_its_children_with_it(populated):
    document = definition_document(populated)
    document["pages"][0]["condition"] = "!!! not jmespath"
    document["pages"][0]["sections"][0]["questions"][0]["validators"][0]["validator"] = "nope"

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert [issue.path for issue in raised.value.issues] == ["pages.0"]


def test_an_unknown_widget_is_reported_rather_than_ignored(populated):
    document = definition_document(populated)
    document["pages"][0]["sections"][0]["questions"][0]["widget"] = "carousel"

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert raised.value.issues[0].errors["widget"]


def test_a_document_for_another_questionnaire_is_refused(populated):
    document = definition_document(populated)
    document["questionnaire"]["key"] = "something-else"

    with pytest.raises(DefinitionError):
        apply_definition(populated, document)


def test_a_column_count_for_an_unknown_range_is_refused(populated):
    document = definition_document(populated)
    document["columns"] = {"widescreen": 24}

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert raised.value.issues[0].path == "columns"


# ------------------------------------------------------- acknowledged edits


def test_editing_a_version_with_responses_needs_an_acknowledgement(populated):
    QuestionnaireResponse.objects.create(questionnaire_version=populated)
    document = definition_document(populated)
    document["pages"][0]["sections"][0]["questions"][0]["title"] = "Which flavour?"

    with pytest.raises(DefinitionError) as raised:
        apply_definition(populated, document)

    assert raised.value.issues[0].path == "pages.0.sections.0.questions.0"
    assert Question.objects.get(key="flavour").title == "Favourite flavour"


def test_an_acknowledged_edit_goes_through_and_is_recorded(populated):
    user = get_user_model().objects.create_user(username="author")
    QuestionnaireResponse.objects.create(questionnaire_version=populated)
    document = definition_document(populated)
    document["pages"][0]["sections"][0]["questions"][0]["title"] = "Which flavour?"

    apply_definition(
        populated,
        document,
        acknowledgement=Acknowledgement(user=user, reason="Wording fix"),
    )

    assert Question.objects.get(key="flavour").title == "Which flavour?"
    record = AcknowledgedEdit.objects.get(target_key="flavour")
    assert record.acknowledged_by == user
    assert record.reason == "Wording fix"
    assert record.changes["title"]["to"] == "Which flavour?"


def test_an_unticked_box_is_not_an_acknowledgement(populated):
    QuestionnaireResponse.objects.create(questionnaire_version=populated)
    document = definition_document(populated)
    document["pages"][0]["sections"][0]["questions"][0]["title"] = "Which flavour?"

    with pytest.raises(DefinitionError):
        apply_definition(populated, document, acknowledgement=Acknowledgement(understood=False))


def test_layout_alone_never_needs_acknowledging(populated):
    QuestionnaireResponse.objects.create(questionnaire_version=populated)
    document = definition_document(populated)
    document["pages"][0]["columns"] = {"mobile": 6}

    apply_definition(populated, document)

    assert definition_document(populated)["pages"][0]["columns"] == {"mobile": 6}


# ------------------------------------------------------------------ catalog


def test_the_catalog_describes_what_an_author_can_pick(populated):
    catalog = editor_catalog()

    types = {entry["key"] for entry in catalog["questionTypes"]}
    assert QuestionType.SINGLE_CHOICE in types
    single_choice = next(
        entry for entry in catalog["questionTypes"] if entry["key"] == QuestionType.SINGLE_CHOICE
    )
    assert single_choice["supportsChoices"] is True

    required = next(entry for entry in catalog["validators"] if entry["key"] == "required")
    assert required["paramsSchema"]["type"] == "object"
    assert [error["key"] for error in required["errorKeys"]]
    assert json.loads(json.dumps(catalog))


def test_the_catalog_lists_the_questionnaires_a_question_could_nest(populated):
    catalog = editor_catalog()

    assert [entry["key"] for entry in catalog["questionnaires"]] == ["intake"]
    assert catalog["questionnaires"][0]["versions"][0]["version"] == 1


def test_sections_are_matched_by_key_within_their_page(populated):
    document = definition_document(populated)
    document["pages"][0]["sections"].append(
        {
            "key": "extra",
            "title": "Extra",
            "description": "",
            "conclusion": "",
            "defaultState": "closed",
            "condition": "",
            "columns": {},
            "questions": [],
        }
    )

    apply_definition(populated, document)

    assert [section.key for section in Section.objects.all()] == ["basics", "extra"]
