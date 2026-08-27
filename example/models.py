"""A model for the response mappings to write to.

The point of the content type framework here is that the package knows nothing
about this: it is an ordinary model of the example project, and a mapping fills
it in from a questionnaire without either side importing the other.
"""

from __future__ import annotations

from django.db import models


class Lead(models.Model):
    """A prospective client, as the onboarding questionnaire describes one."""

    email = models.EmailField(unique=True)
    contact_name = models.CharField(max_length=255, blank=True, default="")
    company = models.CharField(max_length=255, blank=True, default="")
    company_size = models.CharField(max_length=50, blank=True, default="")
    budget = models.PositiveIntegerField(null=True, blank=True)
    interests = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=50, blank=True, default="")
    questionnaire_response = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.company or self.contact_name or self.email}"
