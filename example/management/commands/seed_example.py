"""Build the example questionnaire.

A management command rather than a JSON fixture on purpose: it goes through
``save()``, so everything the package validates -- widget props against their
schema, validators against their params schema, conditions that parse -- is
checked while the data is built, and there are no primary keys to collide.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from example.models import Lead
from vinta_django_questionnaires.models import (
    EditPolicy,
    FieldRole,
    IntegrationTrigger,
    LayerColumns,
    MappingField,
    MappingOperation,
    Page,
    Question,
    QuestionChoice,
    QuestionMinimumColumns,
    Questionnaire,
    QuestionnaireVersion,
    QuestionnaireWidget,
    QuestionValidator,
    ResponseMapping,
    ResponseWebhook,
    Section,
    ValueSet,
    ValueSetOption,
    ValueSetSource,
    WidgetQuestionType,
    WindowSizeRange,
)
from vinta_django_questionnaires.question_types import QuestionType

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo"

#: The widget keys are the design system's component names, and the props
#: schemas are those components' props -- so a question's widget props land on
#: the React component with nothing in between.
WIDGETS: list[dict[str, Any]] = [
    {
        "key": "input",
        "name": "Input",
        "props_schema": {
            "type": "object",
            "properties": {
                "placeholder": {"type": "string"},
                "type": {"enum": ["text", "email", "url", "tel"]},
                "autoComplete": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "types": [(QuestionType.FREE_TEXT, True), (QuestionType.URL, True)],
    },
    {
        "key": "textarea",
        "name": "Textarea",
        "props_schema": {
            "type": "object",
            "properties": {
                "rows": {"type": "integer", "minimum": 2, "maximum": 20},
                "placeholder": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "default_props": {"rows": 4},
        "types": [(QuestionType.FREE_TEXT, False)],
    },
    {
        "key": "radio-group",
        "name": "Radio group",
        "props_schema": {
            "type": "object",
            "properties": {"orientation": {"enum": ["vertical", "horizontal"]}},
            "additionalProperties": False,
        },
        "default_props": {"orientation": "vertical"},
        "types": [(QuestionType.SINGLE_CHOICE, True)],
    },
    {
        "key": "checkbox-group",
        "name": "Checkbox group",
        "props_schema": {
            "type": "object",
            "properties": {"columns": {"type": "integer", "minimum": 1, "maximum": 4}},
            "additionalProperties": False,
        },
        "default_props": {"columns": 1},
        "types": [(QuestionType.MULTIPLE_CHOICE, True)],
    },
    {
        "key": "combobox",
        "name": "Combobox",
        "props_schema": {
            "type": "object",
            "properties": {
                "placeholder": {"type": "string"},
                "searchPlaceholder": {"type": "string"},
                "emptyText": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "types": [(QuestionType.SINGLE_SELECT, True), (QuestionType.MULTI_SELECT, True)],
    },
    {
        "key": "number-input",
        "name": "Number input",
        "props_schema": {
            "type": "object",
            "properties": {"prefix": {"type": "string"}, "step": {"type": "number"}},
            "additionalProperties": False,
        },
        "types": [(QuestionType.NUMBER, True)],
    },
    {
        "key": "date-range",
        "name": "Date range",
        "props_schema": {
            "type": "object",
            "properties": {"startLabel": {"type": "string"}, "endLabel": {"type": "string"}},
            "additionalProperties": False,
        },
        "default_props": {"startLabel": "From", "endLabel": "Until"},
        "types": [(QuestionType.DATE_RANGE, True)],
    },
    {
        "key": "file-upload",
        "name": "File upload",
        "props_schema": {
            "type": "object",
            "properties": {"accept": {"type": "string"}},
            "additionalProperties": False,
        },
        "types": [(QuestionType.SINGLE_FILE, True)],
    },
    {
        "key": "repeatable-group",
        "name": "Repeatable group",
        "props_schema": {
            "type": "object",
            "properties": {"addLabel": {"type": "string"}, "maxEntries": {"type": "integer"}},
            "additionalProperties": False,
        },
        "types": [(QuestionType.SUB_QUESTIONNAIRE_LIST, True)],
    },
]

BREAKPOINTS: list[dict[str, Any]] = [
    {"key": "mobile", "label": "Phone", "min_width": 0, "max_width": 767, "order": 0},
    {"key": "tablet", "label": "Tablet", "min_width": 768, "max_width": 1023, "order": 1},
    {"key": "desktop", "label": "Desktop", "min_width": 1024, "max_width": None, "order": 2},
]


class Command(BaseCommand):
    help = "Create the example questionnaires, widgets, value sets and a demo user."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the example data first, responses included.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if options["reset"]:
            self._reset()

        user = self._demo_user()
        widgets = self._widgets()
        value_sets = self._value_sets()
        team = self._team_questionnaire(widgets)
        onboarding = self._onboarding_questionnaire(widgets, value_sets, team)
        self._integrations(onboarding)

        self.stdout.write(self.style.SUCCESS("Seeded the example data."))
        self.stdout.write(
            f"  questionnaires: {onboarding.questionnaire.key}, {team.questionnaire.key}"
        )
        self.stdout.write(f"  pages:          {onboarding.pages.count()}")
        self.stdout.write(f"  questions:      {sum(1 for _ in onboarding.iter_questions())}")
        self.stdout.write(f"  widgets:        {QuestionnaireWidget.objects.count()}")
        self.stdout.write(f"  mappings:       {ResponseMapping.objects.count()}")
        self.stdout.write(f"  webhooks:       {ResponseWebhook.objects.count()}")
        self.stdout.write(f"  demo user:      {user.get_username()} / {DEMO_PASSWORD}")

    # -- teardown ----------------------------------------------------------
    def _reset(self) -> None:
        from vinta_django_questionnaires.models import (
            AcknowledgedEdit,
            Answer,
            PageResponse,
            QuestionnaireResponse,
        )

        for model in (Answer, PageResponse, QuestionnaireResponse, AcknowledgedEdit):
            model.objects.all().delete()
        ResponseMapping.objects.all().delete()
        ResponseWebhook.objects.all().delete()
        Lead.objects.all().delete()
        # A question that nests another questionnaire protects it from deletion,
        # so those references go first.
        Question.objects.filter(sub_questionnaire__isnull=False).delete()
        Questionnaire.objects.all().delete()
        QuestionnaireWidget.objects.all().delete()
        ValueSet.objects.all().delete()
        Group.objects.filter(name__startswith="tech-").delete()

    # -- what a finished response turns into -------------------------------
    def _integrations(self, version: QuestionnaireVersion) -> None:
        """A mapping onto the project's own model, and a webhook.

        Neither knows anything about the other, and the package knows nothing
        about `Lead`: the mapping names it through the content type framework
        and fills it in with one JMESPath expression per field.
        """
        mapping, _ = ResponseMapping.objects.update_or_create(
            key="onboarding-lead",
            defaults={
                "name": "Onboarding to Lead",
                "questionnaire": version.questionnaire,
                "content_type": ContentType.objects.get_for_model(Lead),
                "operation": MappingOperation.UPSERT,
                "trigger": IntegrationTrigger.ON_COMPLETION,
                "defaults": {"source": "client-onboarding"},
            },
        )
        mapping.fields.all().delete()
        # The lookup is what makes it an upsert: answer twice from the same
        # address and the same row is updated rather than a second one made.
        MappingField.objects.create(
            mapping=mapping,
            role=FieldRole.LOOKUP,
            target_field="email",
            expression="answers.email",
            is_required=True,
        )
        for order, (target, expression) in enumerate(
            [
                ("contact_name", "answers.full_name"),
                ("company", "answers.company_name"),
                ("company_size", "answers.company_size"),
                ("budget", "answers.budget"),
                ("interests", "answers.services"),
                ("questionnaire_response", "id"),
            ]
        ):
            MappingField.objects.create(
                mapping=mapping, target_field=target, expression=expression, order=order
            )

        # The URL is a template over the same document, and so are the headers
        # and the body.  It is seeded inactive: turning it on reaches the
        # internet, which a seeded example -- and CI -- should not do on its
        # own.  Tick "is active" in the admin to watch the deliveries fill in.
        ResponseWebhook.objects.update_or_create(
            key="onboarding-crm",
            defaults={
                "name": "Tell the CRM",
                "questionnaire": version.questionnaire,
                "trigger": IntegrationTrigger.ON_COMPLETION,
                "is_active": False,
                "method": "POST",
                "url_template": "https://httpbin.org/anything/leads/{company}",
                "url_params": {"company": "answers.company_name || 'unknown'"},
                "headers": {
                    "X-Questionnaire": "client-onboarding",
                    "X-Response": {"$jmespath": "id"},
                },
                "body": {
                    "email": {"$jmespath": "answers.email"},
                    "company": {"$jmespath": "answers.company_name"},
                    "services": {"$jmespath": "answers.services"},
                    "source": "demo",
                },
            },
        )

    # -- supporting records ------------------------------------------------
    def _demo_user(self) -> Any:
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=DEMO_USERNAME)
        if created:
            user.set_password(DEMO_PASSWORD)
            user.is_staff = True
            user.is_superuser = True
            user.save()
        return user

    def _widgets(self) -> dict[str, QuestionnaireWidget]:
        widgets: dict[str, QuestionnaireWidget] = {}
        for spec in WIDGETS:
            widget, _ = QuestionnaireWidget.objects.update_or_create(
                key=spec["key"],
                defaults={
                    "name": spec["name"],
                    "props_schema": spec["props_schema"],
                    "default_props": spec.get("default_props", {}),
                },
            )
            for question_type, is_default in spec["types"]:
                WidgetQuestionType.objects.update_or_create(
                    widget=widget,
                    question_type=question_type,
                    defaults={"is_default": is_default},
                )
            widgets[spec["key"]] = widget
        return widgets

    def _value_sets(self) -> dict[str, ValueSet]:
        sizes, _ = ValueSet.objects.update_or_create(
            key="company-sizes",
            defaults={"name": "Company sizes", "source": ValueSetSource.STATIC},
        )
        for order, (value, label) in enumerate(
            [
                ("1-10", "1 to 10 people"),
                ("11-50", "11 to 50 people"),
                ("51-200", "51 to 200 people"),
                ("200+", "More than 200 people"),
            ]
        ):
            ValueSetOption.objects.update_or_create(
                value_set=sizes, value=value, defaults={"label": label, "order": order}
            )

        # A value set backed by a model, narrowed with the filter DSL.  Groups
        # stand in for whatever a real project would point at.
        for name in ("tech-python", "tech-typescript", "tech-swift", "internal-billing"):
            Group.objects.get_or_create(name=name)
        technologies, _ = ValueSet.objects.update_or_create(
            key="technologies",
            defaults={
                "name": "Technologies",
                "source": ValueSetSource.MODEL,
                "content_type": ContentType.objects.get_for_model(Group),
                "filter_expression": 'name startswith "tech-"',
                "value_field": "name",
                "label_field": "name",
                "ordering": "name",
            },
        )
        return {"company-sizes": sizes, "technologies": technologies}

    # -- the questionnaires ------------------------------------------------
    def _team_questionnaire(self, widgets: dict[str, QuestionnaireWidget]) -> QuestionnaireVersion:
        questionnaire, _ = Questionnaire.objects.update_or_create(
            key="team-member", defaults={"name": "Team member"}
        )
        version, _ = QuestionnaireVersion.objects.update_or_create(
            questionnaire=questionnaire,
            version=1,
            defaults={"title": "Team member", "description": "Someone who will work on this."},
        )
        page, _ = Page.objects.update_or_create(
            questionnaire_version=version,
            key="member",
            defaults={"title": "Team member", "order": 0},
        )
        section, _ = Section.objects.update_or_create(
            page=page, key="details", defaults={"title": "Details", "order": 0}
        )
        name = self._question(
            section,
            key="member_name",
            title="Name",
            question_type=QuestionType.FREE_TEXT,
            order=0,
            widget=widgets["input"],
            widget_props={"placeholder": "Full name", "autoComplete": "name"},
        )
        self._validator(name, "required")
        role = self._question(
            section,
            key="member_role",
            title="Role",
            question_type=QuestionType.SINGLE_CHOICE,
            order=1,
            widget=widgets["radio-group"],
        )
        for order, (value, label) in enumerate(
            [("engineer", "Engineer"), ("designer", "Designer"), ("manager", "Manager")]
        ):
            QuestionChoice.objects.update_or_create(
                question=role,
                axis="option",
                value=value,
                defaults={"label": label, "order": order},
            )
        self._validator(role, "required")
        if not version.is_published:
            version.publish()
        return version

    def _onboarding_questionnaire(
        self,
        widgets: dict[str, QuestionnaireWidget],
        value_sets: dict[str, ValueSet],
        team: QuestionnaireVersion,
    ) -> QuestionnaireVersion:
        questionnaire, _ = Questionnaire.objects.update_or_create(
            key="client-onboarding", defaults={"name": "Client onboarding"}
        )
        version, _ = QuestionnaireVersion.objects.update_or_create(
            questionnaire=questionnaire,
            version=1,
            defaults={
                "title": "Client onboarding",
                "description": "Tell us about **you** and the work you have in mind.",
                "edit_policy": EditPolicy.UNTIL_COMPLETED,
                "responses_due_at": timezone.now() + timedelta(days=30),
            },
        )
        ranges = self._breakpoints(version)
        self._columns(version, ranges, {"mobile": 4, "tablet": 8, "desktop": 12})

        self._about_page(version, ranges, widgets, value_sets)
        self._project_page(version, ranges, widgets, value_sets, team)
        self._billing_page(version, widgets)
        self._extras_page(version, widgets)

        if not version.is_published:
            version.publish()
        return version

    def _about_page(
        self,
        version: QuestionnaireVersion,
        ranges: dict[str, WindowSizeRange],
        widgets: dict[str, QuestionnaireWidget],
        value_sets: dict[str, ValueSet],
    ) -> Page:
        page, _ = Page.objects.update_or_create(
            questionnaire_version=version,
            key="about",
            defaults={
                "title": "About you",
                "description": "The basics, so we know who we are talking to.",
                "order": 0,
            },
        )
        contact, _ = Section.objects.update_or_create(
            page=page, key="contact", defaults={"title": "Contact", "order": 0}
        )

        full_name = self._question(
            contact,
            key="full_name",
            title="Your name",
            question_type=QuestionType.FREE_TEXT,
            order=0,
            widget=widgets["input"],
            widget_props={"placeholder": "Ada Lovelace", "autoComplete": "name"},
        )
        self._validator(full_name, "required")
        self._validator(full_name, "min_length", order=1, params={"minimum": 2})
        self._validator(full_name, "max_length", order=2, params={"maximum": 120})
        self._minimum_columns(full_name, ranges, {"mobile": 4, "tablet": 4, "desktop": 6})

        email = self._question(
            contact,
            key="email",
            title="Work email",
            question_type=QuestionType.FREE_TEXT,
            order=1,
            widget=widgets["input"],
            widget_props={
                "placeholder": "you@company.com",
                "type": "email",
                "autoComplete": "email",
            },
        )
        self._validator(email, "required")
        self._validator(email, "email", order=1)
        # Registered by this project, not the package.
        self._validator(email, "business_email", order=2)
        self._minimum_columns(email, ranges, {"mobile": 4, "tablet": 4, "desktop": 6})

        company_section, _ = Section.objects.update_or_create(
            page=page,
            key="company",
            defaults={"title": "Your company", "order": 1, "default_state": "open"},
        )
        has_company = self._question(
            company_section,
            key="has_company",
            title="Are you asking on behalf of a company?",
            question_type=QuestionType.SINGLE_CHOICE,
            order=0,
            widget=widgets["radio-group"],
            widget_props={"orientation": "horizontal"},
        )
        for order, (value, label) in enumerate([("yes", "Yes"), ("no", "No, it is just me")]):
            QuestionChoice.objects.update_or_create(
                question=has_company,
                axis="option",
                value=value,
                defaults={"label": label, "order": order},
            )
        self._validator(has_company, "required")

        company_name = self._question(
            company_section,
            key="company_name",
            title="Company name",
            question_type=QuestionType.FREE_TEXT,
            order=1,
            condition="has_company == 'yes'",
            widget=widgets["input"],
        )
        self._validator(company_name, "required")
        self._validator(company_name, "unique_company_name", order=1)

        company_size = self._question(
            company_section,
            key="company_size",
            title="How many people work there?",
            question_type=QuestionType.SINGLE_SELECT,
            order=2,
            condition="has_company == 'yes'",
            widget=widgets["combobox"],
            widget_props={"placeholder": "Pick a size", "searchPlaceholder": "Search sizes"},
            value_set=value_sets["company-sizes"],
        )
        self._validator(company_size, "required")
        return page

    def _project_page(
        self,
        version: QuestionnaireVersion,
        ranges: dict[str, WindowSizeRange],
        widgets: dict[str, QuestionnaireWidget],
        value_sets: dict[str, ValueSet],
        team: QuestionnaireVersion,
    ) -> Page:
        page, _ = Page.objects.update_or_create(
            questionnaire_version=version,
            key="project",
            defaults={
                "title": "The project",
                "description": "What you would like built.",
                "conclusion": "That is the hard part done.",
                "order": 1,
            },
        )
        self._columns(page, ranges, {"desktop": 12})
        scope, _ = Section.objects.update_or_create(
            page=page, key="scope", defaults={"title": "Scope", "order": 0}
        )
        self._columns(scope, ranges, {"tablet": 8})

        budget = self._question(
            scope,
            key="budget",
            title="Budget",
            description="In US dollars.",
            question_type=QuestionType.NUMBER,
            order=0,
            widget=widgets["number-input"],
            widget_props={"prefix": "$", "step": 1000},
        )
        self._validator(budget, "required")
        self._validator(budget, "min_value", order=1, params={"minimum": 1000})
        self._validator(budget, "max_value", order=2, params={"maximum": 1000000})
        self._minimum_columns(budget, ranges, {"mobile": 4, "tablet": 4, "desktop": 4})

        window = self._question(
            scope,
            key="start_window",
            title="When could it start?",
            question_type=QuestionType.DATE_RANGE,
            order=1,
            widget=widgets["date-range"],
        )
        self._validator(window, "required")
        self._validator(window, "range_ordered", order=1)
        self._minimum_columns(window, ranges, {"mobile": 4, "tablet": 8, "desktop": 8})

        services = self._question(
            scope,
            key="services",
            title="What do you need?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            order=2,
            allows_other=True,
            other_label="Something else",
            widget=widgets["checkbox-group"],
            widget_props={"columns": 2},
        )
        for order, (value, label) in enumerate(
            [
                ("discovery", "Discovery"),
                ("design", "Design"),
                ("backend", "Backend"),
                ("frontend", "Frontend"),
                ("mobile", "Mobile"),
            ]
        ):
            QuestionChoice.objects.update_or_create(
                question=services,
                axis="option",
                value=value,
                defaults={"label": label, "order": order},
            )
        self._validator(services, "min_items", params={"minimum": 1})
        self._validator(services, "max_items", order=1, params={"maximum": 3})

        stack = self._question(
            scope,
            key="stack",
            title="Anything already decided?",
            question_type=QuestionType.MULTI_SELECT,
            order=3,
            widget=widgets["combobox"],
            widget_props={
                "placeholder": "Anything already chosen",
                "searchPlaceholder": "Search technologies",
                "emptyText": "Nothing matches",
            },
            value_set=value_sets["technologies"],
        )
        # Cross-field: only ask for a stack when engineering work is in scope.
        self._validator(
            stack,
            "jmespath_predicate",
            params={"expression": "length(value) <= `3`"},
            message_overrides={"predicate_failed": "Pick at most three."},
        )

        people, _ = Section.objects.update_or_create(
            page=page,
            key="people",
            defaults={"title": "Who is involved", "order": 1, "default_state": "closed"},
        )
        self._question(
            people,
            key="team",
            title="Anyone we should meet?",
            description="Add one entry per person.",
            question_type=QuestionType.SUB_QUESTIONNAIRE_LIST,
            order=0,
            widget=widgets["repeatable-group"],
            widget_props={"addLabel": "Add someone", "maxEntries": 5},
            sub_questionnaire=team.questionnaire,
            sub_questionnaire_version=team,
        )
        return page

    def _billing_page(
        self, version: QuestionnaireVersion, widgets: dict[str, QuestionnaireWidget]
    ) -> Page:
        """Only asked of companies -- the page's own condition decides."""
        page, _ = Page.objects.update_or_create(
            questionnaire_version=version,
            key="billing",
            defaults={
                "title": "Billing",
                "description": "Where the invoices should go.",
                "order": 2,
                "condition": "has_company == 'yes'",
            },
        )
        section, _ = Section.objects.update_or_create(
            page=page, key="invoicing", defaults={"title": "Invoicing", "order": 0}
        )
        billing_email = self._question(
            section,
            key="billing_email",
            title="Billing email",
            question_type=QuestionType.FREE_TEXT,
            order=0,
            widget=widgets["input"],
        )
        self._validator(billing_email, "required")
        self._validator(billing_email, "email", order=1)

        purchase_order = self._question(
            section,
            key="purchase_order",
            title="Purchase order number",
            description="If your finance team needs one on the invoice.",
            question_type=QuestionType.FREE_TEXT,
            order=1,
            widget=widgets["input"],
        )
        self._validator(
            purchase_order,
            "pattern",
            params={"pattern": "^PO-[0-9]{4,}$"},
            message_overrides={"pattern_mismatch": "Purchase orders look like PO-1234."},
        )
        return page

    def _extras_page(
        self, version: QuestionnaireVersion, widgets: dict[str, QuestionnaireWidget]
    ) -> Page:
        page, _ = Page.objects.update_or_create(
            questionnaire_version=version,
            key="extras",
            defaults={
                "title": "Anything else",
                "description": "Skip this one and come back to it if you would rather.",
                "order": 3,
                "is_skippable": True,
            },
        )
        section, _ = Section.objects.update_or_create(
            page=page, key="notes", defaults={"title": "Notes", "order": 0}
        )
        notes = self._question(
            section,
            key="notes",
            title="Anything you want to add?",
            question_type=QuestionType.FREE_TEXT,
            order=0,
            widget=widgets["textarea"],
            widget_props={"rows": 6},
        )
        self._validator(notes, "max_length", params={"maximum": 500})

        brief = self._question(
            section,
            key="brief",
            title="A brief, if you have one",
            question_type=QuestionType.SINGLE_FILE,
            order=1,
            widget=widgets["file-upload"],
            widget_props={"accept": ".pdf,.md"},
        )
        self._validator(brief, "max_file_size", params={"max_bytes": 5 * 1024 * 1024})
        self._validator(
            brief,
            "allowed_content_types",
            order=1,
            params={"content_types": ["application/pdf", "text/markdown"]},
        )
        return page

    # -- small helpers -----------------------------------------------------
    def _breakpoints(self, version: QuestionnaireVersion) -> dict[str, WindowSizeRange]:
        ranges: dict[str, WindowSizeRange] = {}
        for spec in BREAKPOINTS:
            window_size_range, _ = WindowSizeRange.objects.update_or_create(
                questionnaire_version=version,
                key=spec["key"],
                defaults={
                    "label": spec["label"],
                    "min_width": spec["min_width"],
                    "max_width": spec["max_width"],
                    "order": spec["order"],
                },
            )
            ranges[spec["key"]] = window_size_range
        return ranges

    def _columns(
        self, layer: Any, ranges: dict[str, WindowSizeRange], columns: dict[str, int]
    ) -> None:
        owner = {
            QuestionnaireVersion: "questionnaire_version",
            Page: "page",
            Section: "section",
        }[type(layer)]
        for key, count in columns.items():
            LayerColumns.objects.update_or_create(
                window_size_range=ranges[key],
                **{owner: layer},
                defaults={"columns": count},
            )

    def _minimum_columns(
        self, question: Question, ranges: dict[str, WindowSizeRange], columns: dict[str, int]
    ) -> None:
        for key, count in columns.items():
            QuestionMinimumColumns.objects.update_or_create(
                question=question,
                window_size_range=ranges[key],
                defaults={"minimum_columns": count},
            )

    def _question(self, section: Section, *, key: str, **fields: Any) -> Question:
        question, _ = Question.objects.update_or_create(section=section, key=key, defaults=fields)
        return question

    def _validator(
        self,
        question: Question,
        validator: str,
        *,
        order: int = 0,
        params: dict[str, Any] | None = None,
        message_overrides: dict[str, str] | None = None,
    ) -> QuestionValidator:
        binding, _ = QuestionValidator.objects.update_or_create(
            question=question,
            validator=validator,
            defaults={
                "order": order,
                "params": params or {},
                "message_overrides": message_overrides or {},
            },
        )
        return binding
