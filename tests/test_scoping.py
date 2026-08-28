"""Scopes: what they hold, what they refuse, and what they narrow.

This module runs against the scope model the package ships.  The other half --
a project that points ``QUESTIONNAIRES_SCOPE_MODEL`` at its own -- needs its own
settings module and its own pytest run, and lives in ``tests/scoped``.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from vinta_django_questionnaires.models import (
    Questionnaire,
    QuestionnaireResponse,
    QuestionnaireScope,
    QuestionnaireVersion,
    ScopeType,
    ValueSet,
    VersionStatus,
    get_global_scope,
)
from vinta_django_questionnaires.reporting import response_queryset
from vinta_django_questionnaires.scoping import GLOBAL_SCOPE_KEY, ScopeFilter
from vinta_django_questionnaires.submissions import start_response


def make_scope(key: str, label: str = "") -> QuestionnaireScope:
    scope = QuestionnaireScope(label=label)
    scope.scope = key
    scope.save()
    return scope


@pytest.fixture
def acme(db):
    return make_scope("acme", "Acme")


@pytest.fixture
def globex(db):
    return make_scope("globex", "Globex")


# ------------------------------------------------------------------ the model


def test_a_scope_key_is_derived_rather_than_stored_by_hand(acme):
    assert acme.scope_key == "acme"
    assert acme.scope_type == ScopeType.SCOPED


def test_the_global_scope_is_made_once_and_found_again(db):
    first = get_global_scope()
    second = get_global_scope()

    assert first.pk == second.pk
    assert first.scope_key == GLOBAL_SCOPE_KEY
    assert first.scope is None


def test_a_scope_whose_type_and_value_disagree_is_refused(db):
    scope = QuestionnaireScope(scope_type=ScopeType.SCOPED, _scope="")

    with pytest.raises(ValidationError) as error:
        scope.save()

    assert "scope_type" in error.value.message_dict


def test_two_scopes_cannot_share_a_key(acme):
    with pytest.raises(ValidationError):
        make_scope("acme")


# -------------------------------------------------------------- what it holds


def test_a_questionnaire_lands_in_the_global_scope_by_default(db):
    questionnaire = Questionnaire.objects.create(key="intake")

    assert questionnaire.scope.scope_key == GLOBAL_SCOPE_KEY
    assert questionnaire.scope.scope_type == ScopeType.GLOBAL


def test_two_tenants_can_each_have_an_intake(acme, globex):
    Questionnaire.objects.create(scope=acme, key="intake")
    Questionnaire.objects.create(scope=globex, key="intake")

    assert Questionnaire.objects.filter(key="intake").count() == 2


def test_one_tenant_still_cannot_have_two(acme):
    Questionnaire.objects.create(scope=acme, key="intake")

    with pytest.raises(ValidationError):
        Questionnaire.objects.create(scope=acme, key="intake")


def test_the_database_refuses_it_even_when_full_clean_is_skipped(acme):
    Questionnaire.objects.create(scope=acme, key="intake")

    with pytest.raises(IntegrityError):
        Questionnaire(scope=acme, key="intake").save(validate=False)


def test_value_sets_are_scoped_the_same_way(acme, globex):
    ValueSet.objects.create(scope=acme, key="countries", name="Countries")
    ValueSet.objects.create(scope=globex, key="countries", name="Countries")

    assert ValueSet.objects.filter(key="countries").count() == 2


# ------------------------------------------------------------- immutability


def test_a_scope_cannot_be_changed(acme, globex):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    questionnaire.scope = globex

    with pytest.raises(ValidationError) as error:
        questionnaire.save()

    assert "scope" in error.value.message_dict


def test_saving_a_questionnaire_without_touching_its_scope_is_fine(acme):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    questionnaire = Questionnaire.objects.get(pk=questionnaire.pk)

    questionnaire.name = "Intake"
    questionnaire.save()

    assert Questionnaire.objects.get(pk=questionnaire.pk).name == "Intake"


def test_a_response_cannot_be_moved_either(acme, globex):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )
    response = start_response(version)
    response = QuestionnaireResponse.objects.get(pk=response.pk)

    response.scope = globex
    with pytest.raises(ValidationError):
        response.save()


# --------------------------------------------------------- what a response is


def test_a_response_takes_the_questionnaires_scope(acme):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )

    response = start_response(version)

    assert response.scope_id == acme.pk
    assert response.scope_key == "acme"


def test_a_global_questionnaire_collects_answers_for_each_tenant(acme, globex):
    """The shape the whole design turns on: one definition, many owners."""
    questionnaire = Questionnaire.objects.create(key="nps")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="NPS", status=VersionStatus.PUBLISHED
    )

    start_response(version, scope=acme)
    start_response(version, scope=globex)

    assert questionnaire.scope.scope_type == ScopeType.GLOBAL
    assert response_queryset(scopes=ScopeFilter.only("acme")).count() == 1
    assert response_queryset(scopes=ScopeFilter.only("globex")).count() == 1
    assert response_queryset(scopes=ScopeFilter.everything()).count() == 2


def test_the_key_is_copied_onto_the_row_so_a_read_needs_no_join(acme, django_assert_num_queries):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )
    start_response(version)

    queryset = response_queryset(scopes=ScopeFilter.only("acme"))
    with django_assert_num_queries(1):
        assert queryset.count() == 1

    assert 'INNER JOIN "vinta_django_questionnaires_questionnairescope"' not in str(queryset.query)


# ----------------------------------------------------------------- the filter


def test_everything_lets_everything_through(acme):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )
    start_response(version)

    assert response_queryset(scopes=ScopeFilter.everything()).count() == 1


def test_a_filter_naming_no_scopes_lets_nothing_through(acme):
    """ "These scopes, of which there are none" is empty, not unrestricted."""
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )
    start_response(version)

    assert response_queryset(scopes=ScopeFilter.only()).count() == 0


def test_a_response_filter_does_not_fall_back_to_the_global_scope(acme):
    """A response always belongs to somebody, so there is nothing to fall back to."""
    shared = Questionnaire.objects.create(key="nps")
    version = QuestionnaireVersion.objects.create(
        questionnaire=shared, version=1, title="NPS", status=VersionStatus.PUBLISHED
    )
    start_response(version, scope=get_global_scope())
    start_response(version, scope=acme)

    assert response_queryset(scopes=ScopeFilter.only("acme")).count() == 1


def test_a_definition_filter_does_fall_back_to_the_global_scope(acme):
    """What a tenant may *use* includes what the installation shares."""
    Questionnaire.objects.create(scope=acme, key="intake")
    Questionnaire.objects.create(key="nps")

    seen = ScopeFilter.only("acme", include_global=True).apply(
        Questionnaire.objects.all(), field="scope__scope_key"
    )

    assert {entry.key for entry in seen} == {"intake", "nps"}


# ----------------------------------------------------------- integrations


def test_a_webhook_can_be_pinned_to_one_tenant(acme, globex):
    """A shared questionnaire with one webhook would otherwise fire one URL for all."""
    from vinta_django_questionnaires.integrations import webhooks_for
    from vinta_django_questionnaires.models import IntegrationTrigger, ResponseWebhook

    shared = Questionnaire.objects.create(key="nps")
    version = QuestionnaireVersion.objects.create(
        questionnaire=shared, version=1, title="NPS", status=VersionStatus.PUBLISHED
    )
    ResponseWebhook.objects.create(
        questionnaire=shared,
        scope=acme,
        key="acme-crm",
        name="Acme CRM",
        url_template="https://acme.example/hooks/nps",
    )
    ResponseWebhook.objects.create(
        questionnaire=shared,
        key="everyone",
        name="Shared sink",
        url_template="https://example.invalid/hooks/nps",
    )

    for_acme = webhooks_for(
        start_response(version, scope=acme), trigger=IntegrationTrigger.ON_COMPLETION
    )
    for_globex = webhooks_for(
        start_response(version, scope=globex), trigger=IntegrationTrigger.ON_COMPLETION
    )

    assert {hook.key for hook in for_acme} == {"acme-crm", "everyone"}
    assert {hook.key for hook in for_globex} == {"everyone"}


def test_the_expression_document_carries_the_scope(acme):
    from vinta_django_questionnaires.integrations import response_document

    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )

    document = response_document(start_response(version))

    assert document["scope"] == "acme"


# ------------------------------------------------------- resolving the setting


def test_a_setting_that_names_nothing_says_so(settings):
    from django.core.exceptions import ImproperlyConfigured

    from vinta_django_questionnaires.models_registry import get_scope_model

    settings.QUESTIONNAIRES_SCOPE_MODEL = ""
    with pytest.raises(ImproperlyConfigured, match=r"app_label\.ModelName"):
        get_scope_model()


def test_a_setting_of_the_wrong_shape_says_so(settings):
    from django.core.exceptions import ImproperlyConfigured

    from vinta_django_questionnaires.models_registry import get_scope_model

    settings.QUESTIONNAIRES_SCOPE_MODEL = "notdotted"
    with pytest.raises(ImproperlyConfigured, match="must be of the form"):
        get_scope_model()


def test_a_setting_naming_a_model_that_is_not_installed_says_so(settings):
    from django.core.exceptions import ImproperlyConfigured

    from vinta_django_questionnaires.models_registry import get_scope_model

    settings.QUESTIONNAIRES_SCOPE_MODEL = "nosuchapp.NoSuchScope"
    with pytest.raises(ImproperlyConfigured, match="has not been installed"):
        get_scope_model()


def test_the_default_is_installed_rather_than_left_to_an_attribute_error():
    """``Meta.swappable`` reads the setting with a bare getattr, so it must exist."""
    from django.conf import settings as django_settings

    from vinta_django_questionnaires import conf

    assert getattr(django_settings, conf.SCOPE_MODEL) == conf.DEFAULT_SCOPE_MODEL
