"""Telling whether a question is still the same question.

A new version copies everything, so two versions hold different rows even where
nothing changed.  Keys say which question is which; a fingerprint says whether
it still asks the same thing -- which is what lets answers from v1 and v3 be
pooled, and what makes "these versions differ only in page 2" a fact rather
than a hope.

Only what a respondent reads or is measured against counts.  Moving a question,
narrowing it on a phone or swapping its widget leaves the fingerprint alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vinta_django_questionnaires.models import Question, QuestionnaireVersion


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()[:32]


def question_content(question: Question) -> dict[str, Any]:
    """What a question asks, as plain data."""
    value_set = question.value_set if question.value_set_id else None
    sub_questionnaire = question.sub_questionnaire if question.sub_questionnaire_id else None
    return {
        "key": question.key,
        "title": question.title,
        "description": question.description,
        "type": question.question_type,
        "itemType": question.item_question_type,
        "condition": question.condition,
        "allowsOther": question.allows_other,
        "valueSet": value_set.key if value_set else None,
        "subQuestionnaire": sub_questionnaire.key if sub_questionnaire else None,
        "choices": [
            {"axis": choice.axis, "value": choice.value, "label": choice.label}
            for choice in question.choices.all()
        ],
        "validators": [
            {
                "validator": binding.validator,
                "params": binding.params,
                "messages": binding.message_overrides,
                "enabled": binding.is_enabled,
            }
            for binding in question.validators.all()
        ],
    }


def question_fingerprint(question: Question) -> str:
    return _digest(question_content(question))


def version_fingerprint(version: QuestionnaireVersion) -> str:
    """The fingerprint of everything a version asks, in order."""
    return _digest(
        [
            {
                "page": page.key,
                "condition": page.condition,
                "sections": [
                    {
                        "section": section.key,
                        "condition": section.condition,
                        "questions": [
                            question_fingerprint(question) for question in section.questions.all()
                        ],
                    }
                    for section in page.sections.all()
                ],
            }
            for page in version.pages.all()
        ]
    )


@dataclass
class VersionComparison:
    """What changed between two versions, by question key."""

    unchanged: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def is_identical(self) -> bool:
        return not (self.changed or self.added or self.removed)

    def can_pool(self, question_key: str) -> bool:
        """Whether answers to *question_key* mean the same thing in both versions."""
        return question_key in self.unchanged


def compare_versions(
    before: QuestionnaireVersion, after: QuestionnaireVersion
) -> VersionComparison:
    """Compare two versions question by question.

    Use it to decide what can be reported together: a question in
    ``unchanged`` was asked identically in both, so its answers are
    comparable, and one in ``changed`` is not.
    """
    old = _fingerprints_by_key(before)
    new = _fingerprints_by_key(after)
    comparison = VersionComparison(
        added=sorted(set(new) - set(old)),
        removed=sorted(set(old) - set(new)),
    )
    for key in sorted(set(old) & set(new)):
        if old[key] == new[key]:
            comparison.unchanged.append(key)
        else:
            comparison.changed.append(key)
    return comparison


def _fingerprints_by_key(version: QuestionnaireVersion) -> dict[str, str]:
    return {question.key: question_fingerprint(question) for question in version.iter_questions()}
