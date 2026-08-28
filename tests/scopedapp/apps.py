"""A project that has a real tenant boundary, for the swapped-model run."""

from django.apps import AppConfig


class ScopedAppConfig(AppConfig):
    name = "tests.scopedapp"
    label = "scopedapp"
    default_auto_field = "django.db.models.BigAutoField"
