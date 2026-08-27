"""The example project's own app, which exists to carry its commands and admin."""

from __future__ import annotations

from django.apps import AppConfig


class ExampleConfig(AppConfig):
    name = "example"
    label = "example"
    verbose_name = "Questionnaires example"
