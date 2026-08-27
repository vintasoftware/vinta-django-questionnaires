"""Write out what every registered validator promises.

The TypeScript client checks its own registry against this file: a validator
that needs a client implementation and does not have one is a build failure,
not a surprise in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from vinta_django_questionnaires.plan import PLAN_VERSION
from vinta_django_questionnaires.validators import registry
from vinta_django_questionnaires.validators.base import CLIENT_MODE_CHECKS


def build_manifest() -> dict[str, Any]:
    return {
        "planVersion": PLAN_VERSION,
        "validators": [
            {
                "key": key,
                "label": str(validator.label or key),
                "errorKeys": {
                    error_key: str(message)
                    for error_key, message in validator.error_messages.items()
                },
                "paramsSchema": dict(validator.params_schema),
                "supportedQuestionTypes": (
                    sorted(validator.supported_question_types)
                    if validator.supported_question_types is not None
                    else None
                ),
                "skipWhenEmpty": validator.skip_when_empty,
                "readsContext": validator.reads_context,
                "client": {
                    "mode": validator.client.mode,
                    "checks": [
                        {"kind": check.kind, "errorKey": check.error_key, "args": list(check.args)}
                        for check in validator.client.checks
                    ]
                    if validator.client.mode == CLIENT_MODE_CHECKS
                    else [],
                },
            }
            for key, validator in registry.items()
        ],
    }


class Command(BaseCommand):
    help = "Write the validator manifest the TypeScript client checks itself against."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--output", default="-", help="File to write to, or - for stdout.")

    def handle(self, *args: Any, **options: Any) -> None:
        payload = json.dumps(build_manifest(), indent=2, sort_keys=True, ensure_ascii=False)
        destination = options["output"]
        if destination == "-":
            self.stdout.write(payload)
            return
        Path(destination).write_text(payload + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {destination}"))
