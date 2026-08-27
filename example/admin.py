"""Admin for the example project.

The package registers its own admin now, so this is one import plus whatever is
specific to this project -- here, the model the response mappings write into.

A project that wants a different arrangement can unregister what it does not
want, or import the ModelAdmin classes and register them against its own site;
see `vinta_django_questionnaires.admin`.
"""

from __future__ import annotations

from django.contrib import admin

import vinta_django_questionnaires.admin  # noqa: F401  -- registers the package's admin
from example.models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    """Where the onboarding questionnaire's answers end up.

    Nothing here knows about questionnaires: a `ResponseMapping` names this
    model through the content type framework and fills it in with one JMESPath
    expression per field.
    """

    list_display = ("email", "company", "contact_name", "company_size", "budget", "created_at")
    list_filter = ("source", "company_size")
    search_fields = ("email", "company", "contact_name")
    readonly_fields = ("questionnaire_response", "created_at", "updated_at")
