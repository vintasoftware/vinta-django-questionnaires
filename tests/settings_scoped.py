"""Settings for the swapped-model run.

``Meta.swappable`` resolves once per process, so pointing the scope model
somewhere else cannot be an ``override_settings`` -- it needs its own settings
module and its own pytest invocation::

    uv run pytest tests/scoped --ds=tests.settings_scoped

Everything else is the ordinary test project.
"""

from __future__ import annotations

from tests.settings import *  # noqa: F403

INSTALLED_APPS = [
    *[app for app in INSTALLED_APPS if app != "tests.testapp"],  # noqa: F405
    "tests.testapp",
    "tests.scopedapp",
]

#: The whole point of this settings module.
QUESTIONNAIRES_SCOPE_MODEL = "scopedapp.OrganizationScope"
