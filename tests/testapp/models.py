"""Models for the test-only app.

Add the models your package needs to integrate against here.  They live outside the
distribution, so they can be as contrived as the tests require.
"""

from __future__ import annotations

from django.db import models


class Client(models.Model):
    """Somewhere for a response mapping to write to.

    Deliberately ordinary: a mapping should work against a model that knows
    nothing about questionnaires, which is the whole point of naming it through
    the content type framework.
    """

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True, default="")
    company = models.CharField(max_length=255, blank=True, default="")
    headcount = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return self.email
