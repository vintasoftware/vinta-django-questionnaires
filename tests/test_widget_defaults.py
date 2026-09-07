"""The widget set the package ships, and the command that installs it."""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command

from vinta_django_questionnaires.catalog import widget_catalog
from vinta_django_questionnaires.models import QuestionnaireWidget, WidgetQuestionType
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.widget_defaults import DEFAULT_WIDGETS

pytestmark = pytest.mark.django_db


def install(**options: object) -> str:
    out = io.StringIO()
    call_command("install_default_widgets", stdout=out, **options)
    return out.getvalue()


class TestTheDefaultWidgets:
    def test_every_spec_declares_a_key_a_schema_and_a_type(self):
        for spec in DEFAULT_WIDGETS:
            assert spec["key"]
            assert spec["props_schema"]["type"] == "object"
            assert spec["question_types"]

    def test_no_two_widgets_claim_the_same_key(self):
        keys = [spec["key"] for spec in DEFAULT_WIDGETS]

        assert len(keys) == len(set(keys))

    def test_no_two_widgets_claim_the_same_default(self):
        # The database refuses a second default for a question type, so a set
        # that claims one twice cannot be installed at all.
        claimed = [
            question_type
            for spec in DEFAULT_WIDGETS
            for question_type, is_default in spec["question_types"]
            if is_default
        ]

        assert len(claimed) == len(set(claimed))

    def test_every_question_type_has_a_widget(self):
        # Not a rule the model enforces, but a set that leaves a type out means
        # a question of that type falls back to whatever the client guesses.
        covered = {
            question_type
            for spec in DEFAULT_WIDGETS
            for question_type, _is_default in spec["question_types"]
        }

        assert covered == set(QuestionType.values)


class TestInstalling:
    def test_it_creates_the_set(self):
        install()

        assert QuestionnaireWidget.objects.count() == len(DEFAULT_WIDGETS)

    def test_it_can_be_run_again(self):
        install()
        install()

        assert QuestionnaireWidget.objects.count() == len(DEFAULT_WIDGETS)

    def test_a_dry_run_writes_nothing(self):
        output = install(dry_run=True)

        assert "Would install" in output
        assert not QuestionnaireWidget.objects.exists()

    def test_it_leaves_a_project_edit_alone(self):
        install()
        widget = QuestionnaireWidget.objects.get(key="textarea")
        widget.default_props = {"rows": 12}
        widget.save()

        install()

        widget.refresh_from_db()
        assert widget.default_props == {"rows": 12}

    def test_overwrite_puts_the_shipped_values_back(self):
        install()
        QuestionnaireWidget.objects.filter(key="textarea").update(default_props={"rows": 12})

        install(overwrite=True)

        assert QuestionnaireWidget.objects.get(key="textarea").default_props == {"rows": 4}

    def test_it_does_not_take_a_default_another_widget_holds(self):
        mine = QuestionnaireWidget.objects.create(key="mine", name="Mine")
        WidgetQuestionType.objects.create(
            widget=mine, question_type=QuestionType.FREE_TEXT, is_default=True
        )

        install()

        assert (
            WidgetQuestionType.objects.get(
                question_type=QuestionType.FREE_TEXT, is_default=True
            ).widget_id
            == mine.pk
        )

    def test_the_catalog_offers_what_was_installed(self):
        install()

        keys = {entry["key"] for entry in widget_catalog()}
        assert {"input", "radio-group", "checkbox-group", "matrix"} <= keys
