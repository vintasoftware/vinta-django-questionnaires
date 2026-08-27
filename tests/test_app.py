"""Smoke tests: the app loads and the test project checks out.

They keep the suite from being empty, which pytest reports as an error.  Replace
them as real tests arrive.
"""

from __future__ import annotations

import pytest
from django.apps import apps
from django.core.management import call_command


def test_app_is_installed():
    config = apps.get_app_config("vinta_django_questionnaires")

    assert config.name == "vinta_django_questionnaires"


@pytest.mark.django_db  # the JSONField checks probe the database backend's features
def test_system_checks_pass():
    call_command("check", fail_level="WARNING")
