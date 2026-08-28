"""The admin: the structure editor, the response table, and what they refuse."""

from __future__ import annotations

from html.parser import HTMLParser

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse

from tests.conftest import make_question
from vinta_django_questionnaires.admin.structure import StructureEditor
from vinta_django_questionnaires.models import (
    AcknowledgedEdit,
    Page,
    Question,
    QuestionChoice,
    QuestionnaireResponse,
    QuestionnaireVersion,
    QuestionValidator,
    Section,
    VersionStatus,
)
from vinta_django_questionnaires.question_types import QuestionType
from vinta_django_questionnaires.submissions import start_response, submit_page


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        username="author", password="questionnaires", is_staff=True, is_superuser=True
    )


@pytest.fixture
def tree(version, ranges):
    """A version deep enough to exercise every level of the editor."""
    page = Page.objects.create(questionnaire_version=version, key="about", title="About")
    section = Section.objects.create(page=page, key="basics", title="Basics")
    question = make_question(
        section, key="flavour", title="Favourite flavour", question_type=QuestionType.SINGLE_CHOICE
    )
    QuestionChoice.objects.create(question=question, value="vanilla", label="Vanilla")
    QuestionValidator.objects.create(question=question, validator="required")
    return version


def structure_url(version):
    return reverse(
        "admin:vinta_django_questionnaires_questionnaireversion_structure", args=[version.pk]
    )


class FormScraper(HTMLParser):
    """Every input, select and textarea of the rendered page, as a browser sees it.

    Building the payload by hand would test the payload rather than the page:
    what matters is that what the template renders round-trips, blank rows and
    hidden bookkeeping fields included.
    """

    def __init__(self) -> None:
        super().__init__()
        self.data: dict[str, str] = {}
        self._textarea: str | None = None
        self._select: str | None = None
        self._selected: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        name = values.get("name")
        if tag == "input" and name:
            kind = values.get("type", "text")
            if kind in {"checkbox", "radio"} and "checked" not in values:
                return
            self.data[name] = values.get("value") or ("on" if kind == "checkbox" else "")
        elif tag == "textarea" and name:
            self._textarea = name
            self.data.setdefault(name, "")
        elif tag == "select" and name:
            self._select = name
            self._selected = None
            self.data[name] = ""
        elif tag == "option" and self._select and "selected" in values:
            self._selected = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self._textarea = None
        elif tag == "select" and self._select:
            if self._selected is not None:
                self.data[self._select] = self._selected
            self._select = None

    def handle_data(self, data: str) -> None:
        if self._textarea:
            self.data[self._textarea] = self.data.get(self._textarea, "") + data


def rendered_payload(client, url, **overrides):
    """GET the page, read its form back out, and apply the changes under test."""
    scraper = FormScraper()
    scraper.feed(client.get(url).content.decode())
    data = {key: value for key, value in scraper.data.items() if key != "csrfmiddlewaretoken"}
    data.update(overrides)
    return data


# ------------------------------------------------------------------- access


def test_the_structure_editor_needs_a_staff_user(client, tree):
    assert client.get(structure_url(tree)).status_code in {302, 403}


def test_a_staff_user_sees_the_whole_tree(client, staff, tree):
    client.force_login(staff)

    body = client.get(structure_url(tree)).content.decode()

    assert "About" in body
    assert "Basics" in body
    assert "Favourite flavour" in body
    # ...and the choice and the validator that hang off the question.
    assert "vanilla" in body
    assert 'name="pages-0-key"' in body


def test_the_validator_dropdown_is_the_registry(client, staff, tree):
    client.force_login(staff)

    body = client.get(structure_url(tree)).content.decode()

    assert '<option value="required"' in body
    assert '<option value="min_length"' in body


# ------------------------------------------------------------------ editing


def test_one_save_changes_three_levels(client, staff, tree):
    client.force_login(staff)
    page = tree.pages.get()
    section = page.sections.get()
    data = rendered_payload(
        client,
        structure_url(tree),
        **{
            "pages-0-title": "About you",
            f"sections-{page.pk}-0-title": "The basics",
            f"questions-{section.pk}-0-title": "Which flavour?",
            "_save": "1",
        },
    )

    response = client.post(structure_url(tree), data)

    assert response.status_code == 302
    assert Page.objects.get().title == "About you"
    assert Section.objects.get().title == "The basics"
    assert Question.objects.get().title == "Which flavour?"


def test_a_blank_row_adds_a_page(client, staff, tree):
    client.force_login(staff)
    data = rendered_payload(
        client,
        structure_url(tree),
        **{"pages-1-key": "extras", "pages-1-title": "Extras", "_save": "1"},
    )

    client.post(structure_url(tree), data)

    assert [page.key for page in tree.pages.all()] == ["about", "extras"]


def test_the_delete_box_removes_a_section_and_what_is_under_it(client, staff, tree):
    client.force_login(staff)
    page = tree.pages.get()
    data = rendered_payload(
        client, structure_url(tree), **{f"sections-{page.pk}-0-DELETE": "on", "_save": "1"}
    )

    client.post(structure_url(tree), data)

    assert not Section.objects.exists()
    assert not Question.objects.exists()


def test_a_choice_can_be_edited_from_the_same_page(client, staff, tree):
    client.force_login(staff)
    question = Question.objects.get()
    data = rendered_payload(
        client,
        structure_url(tree),
        **{f"choices-{question.pk}-0-label": "Plain vanilla", "_save": "1"},
    )

    client.post(structure_url(tree), data)

    assert QuestionChoice.objects.get().label == "Plain vanilla"


def test_nothing_is_written_when_anything_is_wrong(client, staff, tree):
    client.force_login(staff)
    data = rendered_payload(
        client,
        structure_url(tree),
        **{
            "pages-0-title": "About you",
            "pages-0-condition": "!! not jmespath (",
            "_save": "1",
        },
    )

    response = client.post(structure_url(tree), data)

    assert response.status_code == 200
    assert Page.objects.get().title == "About"


def test_saving_and_keeping_going_stays_on_the_page(client, staff, tree):
    client.force_login(staff)

    response = client.post(
        structure_url(tree), rendered_payload(client, structure_url(tree), _continue="1")
    )

    assert response.status_code == 302
    assert response["Location"].endswith("/structure/")


# ------------------------------------------------- editing what has answers


@pytest.fixture
def answered(tree):
    tree.status = VersionStatus.PUBLISHED
    tree.save()
    response = start_response(tree, external_id="session:1")
    submit_page(response, tree.pages.get(), {"flavour": "vanilla"})
    return tree


def test_an_edit_is_refused_until_the_box_is_ticked(client, staff, answered):
    client.force_login(staff)
    section = answered.pages.get().sections.get()
    data = rendered_payload(
        client,
        structure_url(answered),
        **{f"questions-{section.pk}-0-title": "Which flavour?", "_save": "1"},
    )

    response = client.post(structure_url(answered), data)

    assert response.status_code == 200
    assert Question.objects.get().title == "Favourite flavour"
    assert not AcknowledgedEdit.objects.exists()


def test_ticking_it_goes_through_and_is_recorded(client, staff, answered):
    client.force_login(staff)
    section = answered.pages.get().sections.get()
    data = rendered_payload(
        client,
        structure_url(answered),
        **{
            f"questions-{section.pk}-0-title": "Which flavour?",
            "understood": "on",
            "edit_reason": "Clearer wording",
            "_save": "1",
        },
    )

    response = client.post(structure_url(answered), data)

    assert response.status_code == 302
    assert Question.objects.get().title == "Which flavour?"
    record = AcknowledgedEdit.objects.get()
    assert record.acknowledged_by == staff
    assert record.reason == "Clearer wording"
    assert record.changes["title"]["to"] == "Which flavour?"


def test_the_page_says_how_many_responses_are_at_stake(client, staff, answered):
    client.force_login(staff)

    body = client.get(structure_url(answered)).content.decode()

    assert "already has 1 response" in body
    assert "I understand" in body


def test_reordering_is_an_edit_like_any_other(client, staff, answered):
    """Order lives on the question, and the question is what the gate covers.

    What is genuinely ungated is the responsive grid -- `LayerColumns` and
    `QuestionMinimumColumns` are their own models and not version-scoped -- but
    neither of those is edited from here.
    """
    client.force_login(staff)
    section = answered.pages.get().sections.get()
    data = rendered_payload(
        client, structure_url(answered), **{f"questions-{section.pk}-0-order": "3", "_save": "1"}
    )

    refused = client.post(structure_url(answered), data)
    assert refused.status_code == 200
    assert Question.objects.get().order == 0

    data["understood"] = "on"
    accepted = client.post(structure_url(answered), data)

    assert accepted.status_code == 302
    assert Question.objects.get().order == 3


# ------------------------------------------------------------- the versions


def test_the_questionnaire_list_counts_versions_and_responses(client, staff, answered):
    client.force_login(staff)

    body = client.get(
        reverse("admin:vinta_django_questionnaires_questionnaire_changelist")
    ).content.decode()

    assert "Latest structure" in body
    assert "Responses" in body


def test_starting_a_new_version_forks_the_latest(client, staff, answered):
    client.force_login(staff)
    url = reverse(
        "admin:vinta_django_questionnaires_questionnaire_change",
        args=[answered.questionnaire.pk],
    )

    response = client.post(url, rendered_payload(client, url, _new_version="1"))

    assert response.status_code == 302
    assert response["Location"].endswith("/structure/")
    assert answered.questionnaire.versions.count() == 2
    assert answered.questionnaire.versions.order_by("-version").first().status == "draft"


def test_the_publish_action_publishes(client, staff, tree):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireversion_changelist")

    client.post(url, {"action": "publish", "_selected_action": [str(tree.pk)]})

    tree.refresh_from_db()
    assert tree.status == VersionStatus.PUBLISHED


def test_the_fork_action_starts_a_draft(client, staff, tree):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireversion_changelist")

    client.post(url, {"action": "fork", "_selected_action": [str(tree.pk)]})

    assert QuestionnaireVersion.objects.count() == 2


# ------------------------------------------------------------- the responses


def test_the_response_table_is_staff_only(client, answered):
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_table")

    assert client.get(url).status_code in {302, 403}


def test_the_response_table_shows_a_column_per_question(client, staff, answered):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_table")

    body = client.get(url, {"questionnaire": answered.questionnaire_id}).content.decode()

    assert "Favourite flavour" in body
    assert "vanilla" in body


def test_the_table_takes_the_columns_it_is_given(client, staff, answered):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_table")

    body = client.get(
        url, {"questionnaire": answered.questionnaire_id, "columns": "status"}
    ).content.decode()

    assert "vanilla" not in body
    assert "completed" in body


def test_the_table_exports_the_same_columns(client, staff, answered):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_export")

    response = client.get(
        url, {"questionnaire": answered.questionnaire_id, "columns": "status,flavour"}
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    body = b"".join(response.streaming_content).decode()
    assert body.splitlines()[0] == "Status,Favourite flavour"
    assert "vanilla" in body


def test_the_changelist_action_exports_a_selection(client, staff, answered):
    client.force_login(staff)
    url = reverse("admin:vinta_django_questionnaires_questionnaireresponse_changelist")
    response_pk = QuestionnaireResponse.objects.get().pk

    response = client.post(url, {"action": "export_csv", "_selected_action": [str(response_pk)]})

    assert response.status_code == 200
    assert b"vanilla" in b"".join(response.streaming_content)


def test_a_response_shows_what_it_wrote_and_what_it_set_off(client, staff, answered):
    client.force_login(staff)
    response_pk = QuestionnaireResponse.objects.get().pk
    url = reverse(
        "admin:vinta_django_questionnaires_questionnaireresponse_change", args=[response_pk]
    )

    body = client.get(url).content.decode()

    assert "What this response wrote" in body
    assert "What this response set off" in body


def test_a_response_cannot_be_edited_from_the_admin(client, staff, answered):
    client.force_login(staff)
    response_pk = QuestionnaireResponse.objects.get().pk
    url = reverse(
        "admin:vinta_django_questionnaires_questionnaireresponse_change", args=[response_pk]
    )

    body = client.get(url).content.decode()

    # Django renders the view page rather than the change form.
    assert 'name="_save"' not in body


# ---------------------------------------------------------------- the limit


def test_the_editor_knows_how_many_fields_it_posts(tree):
    editor = StructureEditor(tree)

    # One page, one section, one question, one choice, one validator, plus the
    # blank row each list offers -- comfortably over a hundred inputs already.
    assert editor.field_count > 100


# ------------------------------------------------------------- registering


def test_everything_is_registered_by_default():
    from vinta_django_questionnaires.admin import REGISTRY

    for model, _admin_class in REGISTRY:
        assert admin.site.is_registered(model), model


def test_a_project_can_take_one_back_and_register_its_own(db):
    """The reason registering is opt-out: a project may already have an admin."""
    from vinta_django_questionnaires.admin import register, unregister

    site = admin.AdminSite(name="test-own")
    register(site)
    assert site.is_registered(Question)

    unregister(site)
    assert not site.is_registered(Question)

    class MyQuestionAdmin(admin.ModelAdmin):
        pass

    site.register(Question, MyQuestionAdmin)
    assert isinstance(site._registry[Question], MyQuestionAdmin)


def test_registering_twice_leaves_what_is_already_there_alone():
    from vinta_django_questionnaires.admin import register

    site = admin.AdminSite(name="test-twice")

    class MyQuestionAdmin(admin.ModelAdmin):
        pass

    site.register(Question, MyQuestionAdmin)
    register(site)

    assert isinstance(site._registry[Question], MyQuestionAdmin)
    # ...and everything it did not already have is there.
    assert site.is_registered(Page)


def test_force_replaces_what_is_there():
    from vinta_django_questionnaires.admin import QuestionAdmin, register

    site = admin.AdminSite(name="test-force")

    class MyQuestionAdmin(admin.ModelAdmin):
        pass

    site.register(Question, MyQuestionAdmin)
    register(site, force=True)

    assert isinstance(site._registry[Question], QuestionAdmin)


def test_a_themed_admin_can_put_its_own_base_underneath():
    """What a project on django-unfold needs: its base class, inlines included."""
    from vinta_django_questionnaires.admin import register

    class ThemedModelAdmin(admin.ModelAdmin):
        themed = True

    class ThemedInline(admin.TabularInline):
        themed = True

    site = admin.AdminSite(name="test-themed")
    register(site, model_admin_base=ThemedModelAdmin, inline_base=ThemedInline)

    registered = site._registry[QuestionnaireVersion]
    assert isinstance(registered, ThemedModelAdmin)
    assert registered.__class__.__name__ == "QuestionnaireVersionAdmin"
    assert all(issubclass(inline, ThemedInline) for inline in registered.inlines)
    # The originals are untouched, so one site's theme is not another's.
    from vinta_django_questionnaires.admin import QuestionnaireVersionAdmin

    assert not any(
        issubclass(inline, ThemedInline) for inline in QuestionnaireVersionAdmin.inlines
    )


def test_the_setting_turns_registration_off(settings):
    """The module registers on import, so this checks the switch it reads."""
    from vinta_django_questionnaires.admin import REGISTER_SETTING

    settings.QUESTIONNAIRES_REGISTER_ADMIN = False

    from django.conf import settings as django_settings

    assert getattr(django_settings, REGISTER_SETTING, True) is False


# ---------------------------------------------------------------- the assets


def test_a_changelist_carries_the_stylesheet_its_links_need(client, staff, tree):
    """The shortcut links in `list_display` are `vqa-link`; nothing else loads it."""
    client.force_login(staff)

    body = client.get(
        reverse("admin:vinta_django_questionnaires_questionnaire_changelist")
    ).content.decode()

    assert "vinta_django_questionnaires/admin.css" in body
    assert "vqa-link" in body
