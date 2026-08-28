"""The package running against a scope model it does not own.

Everything here exercises the same behaviour ``tests/test_scoping.py`` does,
against ``scopedapp.OrganizationScope`` instead of the model this package
ships -- which is the only way to find out whether "swappable" is true.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from tests.scopedapp.models import Organization, OrganizationScope
from vinta_django_questionnaires.models import (
    Questionnaire,
    QuestionnaireVersion,
    ScopeType,
    VersionStatus,
    get_global_scope,
)
from vinta_django_questionnaires.models_registry import get_scope_model
from vinta_django_questionnaires.reporting import response_queryset
from vinta_django_questionnaires.scoping import ScopeFilter
from vinta_django_questionnaires.submissions import start_response


@pytest.fixture
def acme(db):
    organization = Organization.objects.create(slug="acme", name="Acme")
    scope = OrganizationScope(label="Acme")
    scope.scope = organization
    scope.save()
    return scope


@pytest.fixture
def globex(db):
    organization = Organization.objects.create(slug="globex", name="Globex")
    scope = OrganizationScope(label="Globex")
    scope.scope = organization
    scope.save()
    return scope


def test_the_setting_is_what_this_run_is_about():
    assert settings.QUESTIONNAIRES_SCOPE_MODEL == "scopedapp.OrganizationScope"
    assert get_scope_model() is OrganizationScope


def test_the_shipped_model_has_no_table_here():
    from vinta_django_questionnaires.models import QuestionnaireScope

    # ``swapped`` is the model that replaced it, not the setting name, and it
    # is what ``admin.register()`` reads to know there is no table to register.
    assert QuestionnaireScope._meta.swapped == "scopedapp.OrganizationScope"


def test_the_key_is_whatever_the_project_says_it_is(acme):
    assert acme.scope_key == str(acme.organization_id)
    assert acme.scope_type == ScopeType.SCOPED


def test_the_global_scope_still_works_without_an_organization(db):
    scope = get_global_scope()

    assert isinstance(scope, OrganizationScope)
    assert scope.organization_id is None
    assert scope.scope_key == ""


def test_the_projects_own_invariant_is_enforced(db):
    scope = OrganizationScope(scope_type=ScopeType.SCOPED, organization=None)

    with pytest.raises(ValidationError):
        scope.save()


def test_questionnaires_hang_off_the_projects_model(acme, globex):
    Questionnaire.objects.create(scope=acme, key="intake")
    Questionnaire.objects.create(scope=globex, key="intake")

    assert Questionnaire.objects.filter(key="intake").count() == 2
    assert acme.vinta_django_questionnaires_questionnaire_set.count() == 1


def test_a_scope_is_still_immutable(acme, globex):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    questionnaire.scope = globex

    with pytest.raises(ValidationError):
        questionnaire.save()


def test_responses_filter_by_the_projects_key(acme, globex):
    shared = Questionnaire.objects.create(key="nps")
    version = QuestionnaireVersion.objects.create(
        questionnaire=shared, version=1, title="NPS", status=VersionStatus.PUBLISHED
    )
    start_response(version, scope=acme)
    start_response(version, scope=globex)

    assert response_queryset(scopes=ScopeFilter.only(acme.scope_key)).count() == 1
    assert response_queryset(scopes=ScopeFilter.everything()).count() == 2


def test_deleting_a_tenant_is_refused_while_it_holds_answers(acme):
    questionnaire = Questionnaire.objects.create(scope=acme, key="intake")
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire, version=1, title="Intake", status=VersionStatus.PUBLISHED
    )
    start_response(version)

    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        acme.delete()


def test_the_shipped_scope_admin_is_not_registered_here():
    """``register()`` skips a model that has no table in this installation."""
    from django.contrib import admin

    from vinta_django_questionnaires.models import Questionnaire, QuestionnaireScope

    assert not admin.site.is_registered(QuestionnaireScope)
    # The rest of the package is registered as usual.
    assert admin.site.is_registered(Questionnaire)
