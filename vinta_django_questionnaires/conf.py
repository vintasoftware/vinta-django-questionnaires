"""Every setting this package reads, in one place, with its default.

Django settings are a flat global namespace, so an installable app has to be a
good citizen in it: prefix everything, default everything that can be
defaulted, and fail with a sentence rather than an ``AttributeError`` for the
ones that cannot.

The names below were previously spelled out in the modules that read them.
They still are -- ``integrations.RUN_SETTING`` and friends now point here --
so nothing that imported them has moved.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

#: The scope model, as ``"app_label.ModelName"``.  Defaults to the one this
#: package ships; a project with a real tenant boundary points it at its own.
SCOPE_MODEL = "QUESTIONNAIRES_SCOPE_MODEL"
DEFAULT_SCOPE_MODEL = "vinta_django_questionnaires.QuestionnaireScope"

#: Whether submitting a response runs the mappings and webhooks attached to it.
RUN_INTEGRATIONS = "QUESTIONNAIRES_RUN_INTEGRATIONS"

#: Dotted path to the callable that actually sends a webhook request.
WEBHOOK_SENDER = "QUESTIONNAIRES_WEBHOOK_SENDER"

#: Whether importing ``vinta_django_questionnaires.admin`` registers everything.
REGISTER_ADMIN = "QUESTIONNAIRES_REGISTER_ADMIN"


def get(name: str, default: Any = None) -> Any:
    """Read one setting, falling back to *default*."""
    return getattr(settings, name, default)


def install_swappable_defaults() -> None:
    """Give the swappable model setting a default, if the project has not.

    ``Meta.swappable`` is not like a normal setting lookup.  Django's migration
    autodetector reads the named setting with a bare ``getattr(settings, name)``
    and lets the ``AttributeError`` escape, which is why ``AUTH_USER_MODEL`` --
    the pattern this follows -- is declared in ``django.conf.global_settings``.
    A third-party app cannot add to that module, so the default has to be put
    into the project's settings instead.

    Timing is what makes this work, and why it lives at import time in
    ``apps.py`` rather than in ``AppConfig.ready``.  ``apps.populate`` runs in
    two phases: it creates every ``AppConfig`` first, importing each app module
    and its ``apps`` module, and only then imports any models.  So this has
    already run by the time a field definition or the autodetector asks for the
    setting, where ``ready()`` would be far too late.

    A project that *has* set it is left alone, which is the whole point: this
    is a default, not an override.
    """
    if not hasattr(settings, SCOPE_MODEL):
        setattr(settings, SCOPE_MODEL, DEFAULT_SCOPE_MODEL)
