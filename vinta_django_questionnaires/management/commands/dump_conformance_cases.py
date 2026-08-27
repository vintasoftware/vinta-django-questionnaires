"""Write the conformance corpus both test suites replay.

Every case carries the value, the expected error keys, and the plan the client
should build its schema from -- so the TypeScript suite needs no Python at test
time, only this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandParser

from vinta_django_questionnaires.plan import PLAN_VERSION, standalone_plan
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.validators import registry

if TYPE_CHECKING:
    from vinta_django_questionnaires.validators.base import BaseValidator, Case


def default_question_type(validator_class: type[BaseValidator]) -> str:
    supported = validator_class.supported_question_types
    if not supported or QuestionType.FREE_TEXT in supported:
        return str(QuestionType.FREE_TEXT)
    return sorted(supported)[0]


def case_payload(validator_class: type[BaseValidator], case: Case) -> dict[str, Any]:
    validator = validator_class(params=case.params)
    question_type = case.question_type or default_question_type(validator_class)
    choices: list[dict[str, Any]] | None = None
    if question_type in {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE}:
        # The corpus never leans on a choice list; an empty one keeps the base
        # type permissive so the case exercises the check itself.
        choices = []
    return {
        "validator": validator_class.key,
        "label": case.label,
        "questionType": question_type,
        "params": case.params,
        "value": case.value,
        "expects": list(case.expects),
        "plan": standalone_plan(
            question_type,
            validator.client_checks(),
            uses_context=validator_class.reads_context,
            choices=choices,
        ),
    }


def build_corpus() -> dict[str, Any]:
    return {
        "planVersion": PLAN_VERSION,
        "cases": [
            case_payload(validator_class, case)
            for _, validator_class in registry.items()
            for case in validator_class.conformance
        ],
    }


class Command(BaseCommand):
    help = "Write the conformance corpus replayed by the Python and TypeScript suites."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--output", default="-", help="File to write to, or - for stdout.")

    def handle(self, *args: Any, **options: Any) -> None:
        payload = json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False)
        destination = options["output"]
        if destination == "-":
            self.stdout.write(payload)
            return
        Path(destination).write_text(payload + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {destination}"))
