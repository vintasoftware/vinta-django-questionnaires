"""The APIs with a scope in the path.

The project decides the URL shape by where it mounts the URLconf; this suite
mounts both, unprefixed and under ``/t/<scope_key>/``, so the two behaviours can
be compared side by side.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from vinta_django_questionnaires.models import (
    Questionnaire,
    QuestionnaireScope,
    QuestionnaireVersion,
    ValueSet,
    ValueSetOption,
    VersionStatus,
)
from vinta_django_questionnaires.submissions import start_response


def make_scope(key: str, label: str = "") -> QuestionnaireScope:
    scope = QuestionnaireScope(label=label or key)
    scope.scope = key
    scope.save()
    return scope


def published(questionnaire: Questionnaire, title: str = "Form") -> QuestionnaireVersion:
    return QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title=title, status=VersionStatus.PUBLISHED
    )


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(
        username="staff", password="questionnaires", is_staff=True
    )


@pytest.fixture
def tenants(db):
    return make_scope("acme", "Acme"), make_scope("globex", "Globex")


@pytest.fixture
def answers_everywhere(tenants):
    """One shared questionnaire, answered by both tenants."""
    acme, globex = tenants
    shared = Questionnaire.objects.create(key="nps", name="NPS")
    version = published(shared, "NPS")
    start_response(version, scope=acme, external_id="acme-1")
    start_response(version, scope=globex, external_id="globex-1")
    return acme, globex, version


def authoring(name: str, scope_key: str | None = None, **kwargs: object) -> str:
    if scope_key is None:
        return reverse(f"questionnaires-authoring:{name}", kwargs=kwargs)
    return reverse(f"scoped-authoring:{name}", kwargs={"scope_key": scope_key, **kwargs})


# ------------------------------------------------------------------ responses


def test_without_a_scope_the_listing_spans_every_tenant(client, staff, answers_everywhere):
    client.force_login(staff)

    body = client.get(authoring("response-list")).json()

    assert body["total"] == 2


def test_a_scoped_url_narrows_to_that_tenant(client, staff, answers_everywhere):
    client.force_login(staff)

    body = client.get(authoring("response-list", "acme")).json()

    assert body["total"] == 1
    assert body["results"][0]["external_id"] == "acme-1"


def test_the_export_is_narrowed_the_same_way(client, staff, answers_everywhere):
    client.force_login(staff)

    response = client.get(authoring("response-export", "globex"))

    text = b"".join(response.streaming_content).decode()
    assert "globex-1" in text
    assert "acme-1" not in text


def test_an_unknown_scope_sees_nothing_rather_than_everything(client, staff, answers_everywhere):
    """The failure mode that matters: a typo must not open the whole table."""
    client.force_login(staff)

    body = client.get(authoring("response-list", "nosuchtenant")).json()

    assert body["total"] == 0


# ---------------------------------------------------------------- definitions


def test_the_version_listing_says_which_scope_each_questionnaire_is_in(client, staff, tenants):
    acme, _globex = tenants
    Questionnaire.objects.create(scope=acme, key="intake", name="Intake")
    Questionnaire.objects.create(key="nps", name="NPS")
    client.force_login(staff)

    body = client.get(authoring("questionnaire-list", "acme")).json()

    found = {entry["key"]: entry for entry in body["questionnaires"]}
    assert found["intake"]["scope"] == "acme"
    assert found["intake"]["isGlobal"] is False
    # The shared one comes along: it is a questionnaire this tenant may use.
    assert found["nps"]["isGlobal"] is True


def test_a_tenant_does_not_see_another_tenants_questionnaires(client, staff, tenants):
    acme, globex = tenants
    Questionnaire.objects.create(scope=acme, key="intake", name="Acme intake")
    Questionnaire.objects.create(scope=globex, key="private", name="Globex only")
    client.force_login(staff)

    body = client.get(authoring("questionnaire-list", "acme")).json()

    assert {entry["key"] for entry in body["questionnaires"]} == {"intake"}


def test_a_tenants_own_questionnaire_shadows_the_shared_one(client, staff, tenants):
    """Most-specific-first, at the one call site where the URL cannot decide."""
    acme, _globex = tenants
    shared = Questionnaire.objects.create(key="intake", name="Shared intake")
    published(shared, "Shared")
    own = Questionnaire.objects.create(scope=acme, key="intake", name="Acme intake")
    published(own, "Acme")
    client.force_login(staff)

    body = client.get(
        authoring("version-definition", "acme", questionnaire_key="intake", version=1)
    ).json()

    assert body["document"]["title"] == "Acme"


def test_without_its_own_a_tenant_gets_the_shared_one(client, staff, tenants):
    shared = Questionnaire.objects.create(key="intake", name="Shared intake")
    published(shared, "Shared")
    client.force_login(staff)

    body = client.get(
        authoring("version-definition", "acme", questionnaire_key="intake", version=1)
    ).json()

    assert body["document"]["title"] == "Shared"


def test_a_new_questionnaire_lands_in_the_url_s_scope(client, staff, tenants):
    client.force_login(staff)

    response = client.post(
        authoring("questionnaire-create", "acme"),
        data=json.dumps({"key": "intake", "name": "Intake"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Questionnaire.objects.get(key="intake").scope.scope_key == "acme"


def test_creating_the_same_key_in_two_tenants_is_allowed(client, staff, tenants):
    client.force_login(staff)
    body = json.dumps({"key": "intake", "name": "Intake"})

    for scope_key in ("acme", "globex"):
        response = client.post(
            authoring("questionnaire-create", scope_key),
            data=body,
            content_type="application/json",
        )
        assert response.status_code == 201

    assert Questionnaire.objects.filter(key="intake").count() == 2


def test_creating_it_twice_in_one_tenant_is_not(client, staff, tenants):
    client.force_login(staff)
    body = json.dumps({"key": "intake", "name": "Intake"})
    client.post(
        authoring("questionnaire-create", "acme"), data=body, content_type="application/json"
    )

    response = client.post(
        authoring("questionnaire-create", "acme"), data=body, content_type="application/json"
    )

    assert response.status_code == 400


def test_the_catalog_only_offers_what_this_tenant_may_use(client, staff, tenants):
    acme, globex = tenants
    ValueSet.objects.create(scope=acme, key="offices", name="Acme offices")
    ValueSet.objects.create(scope=globex, key="regions", name="Globex regions")
    ValueSet.objects.create(key="countries", name="Countries")
    client.force_login(staff)

    body = client.get(authoring("catalog", "acme")).json()

    assert {entry["key"] for entry in body["valueSets"]} == {"offices", "countries"}


# ------------------------------------------------------------- the fill-in API


def test_a_response_opened_through_a_scoped_url_belongs_to_that_tenant(client, tenants):
    _acme, _globex = tenants
    shared = Questionnaire.objects.create(key="nps", name="NPS")
    published(shared, "NPS")
    user = get_user_model().objects.create_user(username="hugo", password="questionnaires")
    client.force_login(user)

    response = client.post(
        reverse("scoped-responses:response-create", kwargs={"scope_key": "acme"}),
        data=json.dumps({"questionnaire": "nps"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    from vinta_django_questionnaires.models import QuestionnaireResponse

    assert QuestionnaireResponse.objects.get().scope_key == "acme"


def test_a_tenant_value_set_shadows_the_shared_one(client, tenants):
    acme, _globex = tenants
    shared = ValueSet.objects.create(key="countries", name="Everywhere")
    ValueSetOption.objects.create(value_set=shared, value="br", label="Brazil", order=0)
    own = ValueSet.objects.create(scope=acme, key="countries", name="Where Acme sells")
    ValueSetOption.objects.create(value_set=own, value="pt", label="Portugal", order=0)
    user = get_user_model().objects.create_user(username="hugo", password="questionnaires")
    client.force_login(user)

    body = client.get(
        reverse(
            "scoped-responses:value-set-options", kwargs={"scope_key": "acme", "key": "countries"}
        )
    ).json()

    assert [option["value"] for option in body["options"]] == ["pt"]


# ----------------------------------------------------------------- the admin


@pytest.fixture
def answered_in_both(tenants):
    """The same key in two tenants, each with an answer -- the merge hazard."""
    acme, globex = tenants
    from tests.conftest import make_question
    from vinta_django_questionnaires.models import Page, Section
    from vinta_django_questionnaires.submissions import submit_page

    made = {}
    for scope, flavour in ((acme, "vanilla"), (globex, "pistachio")):
        questionnaire = Questionnaire.objects.create(scope=scope, key="intake", name="Intake")
        version = published(questionnaire, "Intake")
        page = Page.objects.create(questionnaire_version=version, key="about", title="About")
        section = Section.objects.create(page=page, key="basics", title="Basics")
        make_question(section, key="flavour", title="Favourite flavour")
        response = start_response(version, external_id=f"{scope.scope_key}-1")
        submit_page(response, page, {"flavour": flavour})
        made[scope.scope_key] = questionnaire
    return made


def table_url() -> str:
    return reverse("admin:vinta_django_questionnaires_questionnaireresponse_table")


def test_the_admin_table_spans_every_scope_by_default(client, staff, answers_everywhere):
    client.force_login(staff)

    body = client.get(table_url(), {"columns": "external_id"}).content.decode()

    assert "acme-1" in body
    assert "globex-1" in body


def test_the_admin_scope_control_narrows_it(client, staff, answers_everywhere):
    client.force_login(staff)

    body = client.get(table_url(), {"scope": "acme", "columns": "external_id"}).content.decode()

    assert "acme-1" in body
    assert "globex-1" not in body


def test_two_tenants_with_the_same_key_do_not_select_as_one(client, staff, answered_in_both):
    """What the primary-key filter is for: a key no longer identifies one row."""
    client.force_login(staff)

    body = client.get(table_url(), {"questionnaire": answered_in_both["acme"].pk}).content.decode()

    assert "vanilla" in body
    assert "pistachio" not in body


def test_the_questionnaire_control_says_which_scope_each_one_is_in(
    client, staff, answered_in_both
):
    client.force_login(staff)

    body = client.get(table_url()).content.decode()

    assert "Intake - Acme" in body
    assert "Intake - Globex" in body
