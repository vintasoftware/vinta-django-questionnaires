"""The built-in validator library, and the corpus the client replays."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vinta_django_questionnaires.management.commands.dump_conformance_cases import build_corpus
from vinta_django_questionnaires.management.commands.dump_validation_manifest import build_manifest
from vinta_django_questionnaires.validators import (
    CLIENT_MODE_CHECKS,
    ValidationContext,
    registry,
)

SHARED = Path(__file__).resolve().parent.parent / "shared"

CASES = [
    pytest.param(
        validator_class, case, id=f"{key}-{index}{'-' + case.label if case.label else ''}"
    )
    for key, validator_class in registry.items()
    for index, case in enumerate(validator_class.conformance)
]


@pytest.mark.parametrize(("validator_class", "case"), CASES)
def test_conformance_cases_hold_on_the_server(validator_class, case):
    outcome = validator_class(params=case.params).run(case.value, ValidationContext())

    assert tuple(issue.error_key for issue in outcome.issues) == case.expects


class TestDeclaration:
    @pytest.mark.parametrize(("key", "validator_class"), registry.items())
    def test_every_validator_declares_its_error_messages(self, key, validator_class):
        assert validator_class.error_messages
        assert all(str(message) for message in validator_class.error_messages.values())

    @pytest.mark.parametrize(("key", "validator_class"), registry.items())
    def test_every_native_check_names_a_declared_error_key(self, key, validator_class):
        if validator_class.client.mode != CLIENT_MODE_CHECKS:
            return
        for check in validator_class.client.checks:
            assert check.error_key in validator_class.error_keys()

    @pytest.mark.parametrize(("key", "validator_class"), registry.items())
    def test_every_validator_is_exercised(self, key, validator_class):
        assert validator_class.conformance, f"{key} has no conformance cases"


class TestMessages:
    def test_params_are_interpolated(self):
        validator = registry.get("min_length")(params={"minimum": 4})
        outcome = validator.run("ab", ValidationContext())

        assert outcome.issues[0].message == "Use at least 4 characters."

    def test_an_override_wins(self):
        validator = registry.get("min_length")(
            params={"minimum": 4}, message_overrides={"too_short": "Too short, need {minimum}."}
        )
        outcome = validator.run("ab", ValidationContext())

        assert outcome.issues[0].message == "Too short, need 4."

    def test_the_emitted_message_keeps_the_placeholders_the_failure_fills(self):
        checks = registry.get("max_file_size")(params={"max_bytes": 10}).client_checks()

        assert checks[0]["message"] == "{name} is over the {max_bytes} byte limit."
        assert checks[0]["params"] == {"max_bytes": 10}


class TestContext:
    def test_a_predicate_reads_what_earlier_links_recorded(self):
        context = ValidationContext()
        registry.get("min_length")(params={"minimum": 2}).run("abcd", context)
        outcome = registry.get("jmespath_predicate")(
            params={"expression": "results.min_length.data.length > `3`"}
        ).run("abcd", context)

        assert outcome.is_valid

    def test_a_predicate_reads_sibling_answers(self):
        context = ValidationContext(answers={"has_company": True})
        outcome = registry.get("jmespath_predicate")(
            params={"expression": "answers.has_company"}
        ).run("Vinta", context)

        assert outcome.is_valid


class TestSharedArtifacts:
    def test_the_manifest_on_disk_is_current(self):
        stored = json.loads((SHARED / "validators.json").read_text())

        assert stored == build_manifest(), "run dump_validation_manifest"

    def test_the_corpus_on_disk_is_current(self):
        stored = json.loads((SHARED / "conformance-cases.json").read_text())

        assert stored == build_corpus(), "run dump_conformance_cases"

    def test_every_case_carries_a_plan_the_client_can_build_from(self):
        for case in build_corpus()["cases"]:
            assert case["plan"]["type"]
            assert case["plan"]["checks"]
