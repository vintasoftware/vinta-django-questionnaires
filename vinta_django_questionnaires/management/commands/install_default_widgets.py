"""Create the widget rows the TypeScript client ships components for."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from vinta_django_questionnaires.models import QuestionnaireWidget, WidgetQuestionType
from vinta_django_questionnaires.widget_defaults import DEFAULT_WIDGETS, WidgetSpec


class Command(BaseCommand):
    help = (
        "Install the default widget set. Idempotent: run it again after an "
        "upgrade to pick up widgets a later release added."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Say what would change without writing anything.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help=(
                "Reset the name, description, schema and props of a widget that "
                "already exists. Off by default, so a project's own edits to a "
                "shipped widget survive a re-run."
            ),
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        overwrite: bool = options["overwrite"]
        created = updated = untouched = 0

        for spec in DEFAULT_WIDGETS:
            existing = QuestionnaireWidget.objects.filter(key=spec["key"]).first()
            if existing is None:
                created += 1
                self.stdout.write(f"  + {spec['key']}")
                if not dry_run:
                    self._install(spec)
                continue
            if overwrite:
                updated += 1
                self.stdout.write(f"  ~ {spec['key']}")
                if not dry_run:
                    self._install(spec, widget=existing)
                continue
            # The row is there and is not being reset, but the question types it
            # supports still are: a release that teaches an existing widget a new
            # type would otherwise never reach an installation that already has
            # the widget.
            untouched += 1
            if not dry_run:
                self._support(existing, spec)

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Would install' if dry_run else 'Installed'} the default widgets: "
                f"{created} created, {updated} overwritten, {untouched} left as they were."
            )
        )
        if dry_run:
            # Nothing was written, but `--dry-run` inside an atomic block is only
            # honest if the block cannot commit either.
            transaction.set_rollback(True)

    def _install(
        self, spec: WidgetSpec, widget: QuestionnaireWidget | None = None
    ) -> QuestionnaireWidget:
        widget, _created = QuestionnaireWidget.objects.update_or_create(
            key=spec["key"],
            defaults={
                "name": str(spec["name"]),
                "description": str(spec.get("description", "")),
                "props_schema": spec["props_schema"],
                "default_props": spec.get("default_props", {}),
                "is_active": True,
            },
        )
        self._support(widget, spec)
        return widget

    def _support(self, widget: QuestionnaireWidget, spec: WidgetSpec) -> None:
        """Say which question types this widget renders, and which it defaults for.

        A default is unique per question type across every widget, so claiming
        one that another widget already holds would be refused by the database.
        The first widget to claim a type keeps it, which makes the command safe
        to re-run against a project that moved a default somewhere else.
        """
        for question_type, is_default in spec.get("question_types", []):
            support, created = WidgetQuestionType.objects.get_or_create(
                widget=widget,
                question_type=question_type,
                defaults={"is_default": False},
            )
            if not is_default:
                continue
            claimed = (
                WidgetQuestionType.objects.filter(question_type=question_type, is_default=True)
                .exclude(pk=support.pk)
                .exists()
            )
            if not claimed and not support.is_default:
                support.is_default = True
                support.save(update_fields=["is_default"])
            elif created and claimed:
                self.stdout.write(f"    {question_type}: another widget is already the default.")
