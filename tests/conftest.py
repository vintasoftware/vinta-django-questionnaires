"""Shared fixtures for the Vinta Django Questionnaires test suite."""

from __future__ import annotations

import pytest

from vinta_django_questionnaires.models import (
    Page,
    Question,
    Questionnaire,
    QuestionnaireVersion,
    Section,
    WindowSizeRange,
)
from vinta_django_questionnaires.question_types import QuestionType


@pytest.fixture
def version(db):
    questionnaire = Questionnaire.objects.create(key="intake", name="Intake")
    return QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake form"
    )


@pytest.fixture
def ranges(version):
    return {
        "mobile": WindowSizeRange.objects.create(
            questionnaire_version=version, key="mobile", min_width=0, max_width=767, order=0
        ),
        "desktop": WindowSizeRange.objects.create(
            questionnaire_version=version, key="desktop", min_width=768, order=1
        ),
    }


@pytest.fixture
def section(version):
    page = Page.objects.create(questionnaire_version=version, key="about", title="About you")
    return Section.objects.create(page=page, key="basics", title="Basics")


def make_question(section, **kwargs):
    defaults = {
        "key": "name",
        "title": "Your name",
        "question_type": QuestionType.FREE_TEXT,
    }
    return Question.objects.create(section=section, **{**defaults, **kwargs})
