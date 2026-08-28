"""What a project with organizations does with ``QUESTIONNAIRES_SCOPE_MODEL``.

This is the documented extension point, written the way the README tells a
project to write it -- so if the instructions are wrong, this run fails.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from vinta_django_questionnaires.models import AbstractQuestionnaireScope, ScopeType


class Organization(models.Model):
    """The tenant, as this project understands it."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=255, blank=True, default="")

    def __str__(self) -> str:
        return self.name or self.slug


class OrganizationScope(AbstractQuestionnaireScope):
    """A scope that is an organization, or the installation at large."""

    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        # Deleting a tenant must not take the record of what it collected.
        on_delete=models.PROTECT,
        related_name="questionnaire_scopes",
    )

    class Meta:
        swappable = "QUESTIONNAIRES_SCOPE_MODEL"
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope_type=ScopeType.GLOBAL, organization__isnull=True)
                    | (
                        ~models.Q(scope_type=ScopeType.GLOBAL)
                        & models.Q(organization__isnull=False)
                    )
                ),
                name="organization_scope_type_and_value_agree",
            ),
        ]

    @property
    def scope(self) -> Organization | None:
        return self.organization

    @scope.setter
    def scope(self, value: Organization | None) -> None:
        self.organization = value
        self.scope_type = ScopeType.GLOBAL if value is None else ScopeType.SCOPED

    def build_scope_key(self) -> str:
        # The primary key, not the slug: a key has to be stable for the life of
        # the scope, and a slug is exactly the kind of thing someone renames.
        return "" if self.organization_id is None else str(self.organization_id)
