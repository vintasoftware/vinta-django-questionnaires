"""Walk a response through the whole flow, narrating what the package does.

Run it after ``seed_example`` to see, without a browser: a page rejected by its
validators, a page ruled out by its condition, a page put off for later, a
completed response refusing an edit, a new version forked from the old one, and
an edit made in place with an acknowledgement on the record.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser

from vinta_django_questionnaires.editing import UnacknowledgedEdit, acknowledged_edit
from vinta_django_questionnaires.fingerprints import compare_versions
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    Questionnaire,
    QuestionnaireResponse,
)
from vinta_django_questionnaires.plan import questionnaire_plan
from vinta_django_questionnaires.submissions import (
    PageValidationError,
    ResponseAlreadyCompleted,
    skip_page,
    start_response,
    submit_page,
)
from vinta_django_questionnaires.versioning import new_version_from


class Command(BaseCommand):
    help = "Drive an example response through the flow, printing what happens at each step."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--questionnaire", default="client-onboarding", help="Which questionnaire to fill in."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        questionnaire = self._questionnaire(options["questionnaire"])
        self._reset(questionnaire)
        version = questionnaire.latest_published_version
        if version is None:
            raise CommandError(f"{questionnaire.key} has no published version. Run seed_example.")

        respondent = get_user_model().objects.filter(username="demo").first()
        response = start_response(version, respondent=respondent)
        self._heading(f"Opened a response to {version}")
        self._progress(response)

        self._step("A page is validated as a whole, and rejected as a whole")
        try:
            submit_page(
                response,
                version.pages.get(key="about"),
                {"full_name": "A", "email": "someone@gmail.com", "has_company": "yes"},
            )
        except PageValidationError as error:
            for key, issues in error.validation.as_dict().items():
                for issue in issues:
                    self.stdout.write(f"    {key}: {issue['message']}  [{issue['errorKey']}]")
        self.stdout.write("    nothing was written:")
        self._progress(response)

        self._step("Answering it properly moves the respondent on")
        submit_page(
            response,
            version.pages.get(key="about"),
            {
                "full_name": "Ada Lovelace",
                "email": "ada@analytical.example",
                "has_company": "no",
            },
        )
        self._progress(response)
        self.stdout.write(
            "    billing was never asked: its condition needs a company, so it is on"
        )
        self.stdout.write("    the record as skipped, with the reason.")

        self._step("Changing that answer brings the page back")
        submit_page(
            response,
            version.pages.get(key="about"),
            {
                "full_name": "Ada Lovelace",
                "email": "ada@analytical.example",
                "has_company": "yes",
                "company_name": "Analytical Engines",
                "company_size": "11-50",
            },
        )
        self._progress(response)

        self._step("Filling in the rest")
        submit_page(
            response,
            version.pages.get(key="project"),
            {
                "budget": 60000,
                "start_window": {"start": "2026-10-01", "end": "2026-12-01"},
                "services": ["discovery", "backend"],
                "stack": ["tech-python"],
                "team": [{"member_name": "Charles Babbage", "member_role": "engineer"}],
            },
        )
        submit_page(
            response,
            version.pages.get(key="billing"),
            {"billing_email": "finance@analytical.example", "purchase_order": "PO-2026"},
        )
        self._progress(response)

        self._step("A skippable page can be left for later")
        skip_page(response, version.pages.get(key="extras"))
        self._progress(response)
        self.stdout.write("    still pending: skipping means later, not never.")

        self._step("Coming back to it completes the response")
        submit_page(response, version.pages.get(key="extras"), {"notes": "Looking forward to it."})
        response.refresh_from_db()
        self._progress(response)

        self._step("A completed response refuses an edit, because this version says so")
        try:
            submit_page(
                response,
                version.pages.get(key="extras"),
                {"notes": "One more thought."},
            )
        except ResponseAlreadyCompleted as error:
            self.stdout.write(f"    refused: {error}")
        self.stdout.write(f"    edit policy: {version.edit_policy}")

        self._step("Changing the questionnaire: the ordinary way is a new version")
        draft = new_version_from(version)
        self.stdout.write(f"    forked {version} into {draft} ({draft.status})")
        comparison = compare_versions(version, draft)
        self.stdout.write(f"    identical so far: {comparison.is_identical}")
        question = (
            draft.pages.get(key="about").sections.get(key="contact").questions.get(key="email")
        )
        question.title = "Work email address"
        question.save()
        comparison = compare_versions(version, draft)
        self.stdout.write(f"    after editing the draft, changed: {comparison.changed}")
        self.stdout.write(f"    answers still comparable for: {comparison.unchanged}")

        self._step("Editing the live version in place is possible, but on the record")
        live = (
            version.pages.get(key="about").sections.get(key="contact").questions.get(key="email")
        )
        live.title = "Work email address"
        try:
            live.save()
        except UnacknowledgedEdit as error:
            self.stdout.write(f"    refused: {error.messages[0]}")
        with acknowledged_edit(user=respondent, reason="Wording was ambiguous"):
            live.save()
        record = AcknowledgedEdit.objects.latest("created_at")
        self.stdout.write(
            f"    recorded: {record.action} {record.target_key} by {record.acknowledged_by}"
        )
        self.stdout.write(f"    changed:  {record.changes}")
        self.stdout.write(f"    responses already in at that point: {record.responses_at_edit}")

        self._step("What the browser gets")
        plan = questionnaire_plan(version)
        checks = sum(
            len(question["checks"])
            for page in plan["pages"]
            for section in page["sections"]
            for question in section["questions"]
        )
        self.stdout.write(f"    {len(plan['pages'])} pages, {checks} checks, all with messages")
        self.stdout.write("    POST it to /api/questionnaires/responses/ to do this over HTTP.")

    # -- output ------------------------------------------------------------
    def _reset(self, questionnaire: Questionnaire) -> None:
        """Put the questionnaire back as seeded, so this can be run again.

        The run leaves marks on purpose -- a response, a forked version, an
        edit on the record -- and one of the validators refuses a company name
        that is already registered, so a second run needs a clean start.
        """
        QuestionnaireResponse.objects.filter(
            questionnaire_version__questionnaire=questionnaire
        ).delete()
        AcknowledgedEdit.objects.filter(
            questionnaire_version__questionnaire=questionnaire
        ).delete()
        questionnaire.versions.exclude(version=1).delete()
        call_command("seed_example", stdout=StringIO())

    def _questionnaire(self, key: str) -> Questionnaire:
        questionnaire = Questionnaire.objects.filter(key=key).first()
        if questionnaire is None:
            raise CommandError(f"No questionnaire {key!r}. Run seed_example first.")
        return questionnaire

    def _heading(self, text: str) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{text}"))

    def _step(self, text: str) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{text}"))

    def _progress(self, response: Any) -> None:
        progress = response.progress()
        self.stdout.write(f"    current:   {progress['current']}")
        self.stdout.write(f"    completed: {progress['completed']}")
        self.stdout.write(f"    skipped:   {progress['skipped']}")
        self.stdout.write(f"    pending:   {progress['pending']}")
