"""Resolving the swappable scope model, the ``get_user_model`` way.

``settings.QUESTIONNAIRES_SCOPE_MODEL`` holds an ``"app_label.ModelName"``
string.  Field definitions can use that string directly, but runtime code needs
the class -- and must not import *the model* at module scope, because this
package's modules are imported while the app registry is still populating.
Everything here resolves lazily, at call time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

from vinta_django_questionnaires import conf

if TYPE_CHECKING:
    from django.db import models


def _resolve(setting_name: str, default: str) -> type[models.Model]:
    """Resolve one ``app_label.ModelName`` setting to the model class."""
    value = conf.get(setting_name, default)
    if not value:
        raise ImproperlyConfigured(
            f"{setting_name} must be an 'app_label.ModelName' string, not {value!r}."
        )
    try:
        return apps.get_model(value, require_ready=False)
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"{setting_name} must be of the form 'app_label.ModelName', got {value!r}."
        ) from exc
    except LookupError as exc:
        raise ImproperlyConfigured(
            f"{setting_name} refers to model {value!r} that has not been installed."
        ) from exc


def get_scope_model() -> type[models.Model]:
    """The scope model this installation uses."""
    return _resolve(conf.SCOPE_MODEL, conf.DEFAULT_SCOPE_MODEL)


__all__ = ["get_scope_model"]
