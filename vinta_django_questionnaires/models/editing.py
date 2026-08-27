"""The record of an edit made in place on a version that has responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.editing import (
    Acknowledgement,
    UnacknowledgedEdit,
    current_acknowledgement,
)
from vinta_django_questionnaires.models.base import BaseModel

if TYPE_CHECKING:
    from vinta_django_questionnaires.models.questionnaires import QuestionnaireVersion

#: Bookkeeping fields, which say nothing about what a question asks.
IGNORED_FIELDS = frozenset({"id", "created_at", "updated_at"})


class EditAction(models.TextChoices):
    CREATED = "created", _("Created")
    UPDATED = "updated", _("Updated")
    DELETED = "deleted", _("Deleted")


class AcknowledgedEdit(BaseModel):
    """Someone changed a live definition, and said they meant to.

    The diff is the point: what an existing response now means differently is
    exactly what changed here.  The target is kept both as a relation and as a
    label and key, so a deletion leaves a record that still reads.
    """

    questionnaire_version = models.ForeignKey(
        "vinta_django_questionnaires.QuestionnaireVersion",
        on_delete=models.CASCADE,
        related_name="acknowledged_edits",
        verbose_name=_("questionnaire version"),
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("model")
    )
    object_id = models.PositiveBigIntegerField(_("object id"), null=True, blank=True)
    target = GenericForeignKey("content_type", "object_id")
    target_label = models.CharField(_("target"), max_length=100)
    target_key = models.CharField(_("target key"), max_length=255, blank=True, default="")
    action = models.CharField(_("action"), max_length=10, choices=EditAction.choices)
    changes = models.JSONField(
        _("changes"),
        default=dict,
        blank=True,
        help_text=_("Each changed field, with the value before and after."),
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="acknowledged_questionnaire_edits",
        null=True,
        blank=True,
        verbose_name=_("acknowledged by"),
    )
    reason = models.TextField(_("reason"), blank=True, default="")
    responses_at_edit = models.PositiveIntegerField(
        _("responses at edit"),
        default=0,
        help_text=_("How many responses the version already had when this was done."),
    )

    class Meta:
        verbose_name = _("acknowledged edit")
        verbose_name_plural = _("acknowledged edits")
        ordering = ["-created_at", "pk"]
        indexes = [models.Index(fields=["questionnaire_version", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.target_label} {self.target_key}".strip()


@dataclass
class PendingEdit:
    """What is known about an edit before it is written."""

    version: QuestionnaireVersion
    action: str
    changes: dict[str, dict[str, Any]]
    acknowledgement: Acknowledgement
    responses_at_edit: int


def _serializable(value: Any) -> Any:
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


class VersionScopedModel(models.Model):
    """A definition row whose edits can change what existing responses mean.

    Layout -- how many columns a section takes on a phone -- is deliberately
    not covered: moving a question around does not change what its answer
    meant.  What is covered is everything a respondent reads or is measured
    against: pages, sections, questions, their choices and their validators.
    """

    class Meta:
        abstract = True

    def save(
        self, *args: Any, acknowledgement: Acknowledgement | None = None, **kwargs: Any
    ) -> None:
        action = EditAction.UPDATED if self.pk is not None else EditAction.CREATED
        pending = self._pending_edit(acknowledgement, action=action)
        # `clean()` gates too, so that forms report this as a field error rather
        # than blowing up at save time.  Tell it what this save already knows.
        self._acknowledgement_in_force = pending.acknowledgement if pending else None
        try:
            super().save(*args, **kwargs)
        finally:
            self._acknowledgement_in_force = None
        if pending is not None:
            self._write_edit(pending)

    def clean(self) -> None:
        super().clean()
        action = EditAction.UPDATED if self.pk is not None else EditAction.CREATED
        if self._is_gated(action) and not self._resolve_acknowledgement(None):
            raise UnacknowledgedEdit(self)

    def delete(
        self, *args: Any, acknowledgement: Acknowledgement | None = None, **kwargs: Any
    ) -> Any:
        pending = self._pending_edit(acknowledgement, action=EditAction.DELETED)
        if pending is not None:
            self._write_edit(pending)
        return super().delete(*args, **kwargs)

    def get_edited_version(self) -> QuestionnaireVersion | None:
        """The version this row belongs to, or ``None`` while it is unattached."""
        raise NotImplementedError

    def requires_acknowledgement(self) -> bool:
        """Whether editing this now needs someone to say they mean it.

        The line is the first response.  Before that there is nothing to
        reinterpret, so authors can correct a live version freely.  Override to
        draw it somewhere else -- at publication, say.
        """
        version = self.get_edited_version()
        return version is not None and version.responses.exists()

    def edit_key(self) -> str:
        return str(getattr(self, "key", "") or "")

    def changed_fields(self) -> dict[str, dict[str, Any]]:
        """What this save would change, compared to what is stored."""
        if self.pk is None:
            return {}
        stored = type(self)._default_manager.filter(pk=self.pk).first()
        if stored is None:
            return {}
        changes: dict[str, dict[str, Any]] = {}
        for field in self._meta.concrete_fields:
            if field.name in IGNORED_FIELDS:
                continue
            before = getattr(stored, field.attname)
            after = getattr(self, field.attname)
            if before != after:
                changes[field.name] = {
                    "from": _serializable(before),
                    "to": _serializable(after),
                }
        return changes

    def _resolve_acknowledgement(self, explicit: Acknowledgement | None) -> Acknowledgement | None:
        return (
            explicit
            or getattr(self, "_acknowledgement_in_force", None)
            or current_acknowledgement()
        )

    def _is_gated(self, action: str) -> bool:
        if not self.requires_acknowledgement():
            return False
        # Saving without changing anything is not an edit.
        return not (action == EditAction.UPDATED and not self.changed_fields())

    def _pending_edit(
        self, acknowledgement: Acknowledgement | None, *, action: str
    ) -> PendingEdit | None:
        if not self._is_gated(action):
            return None
        acknowledgement = self._resolve_acknowledgement(acknowledgement)
        if not acknowledgement:
            raise UnacknowledgedEdit(self)
        version = self.get_edited_version()
        if version is None:  # pragma: no cover -- requires_acknowledgement said otherwise
            return None
        return PendingEdit(
            version=version,
            action=action,
            changes=self.changed_fields(),
            acknowledgement=acknowledgement,
            responses_at_edit=version.responses.count(),
        )

    def _write_edit(self, pending: PendingEdit) -> AcknowledgedEdit:
        return AcknowledgedEdit.objects.create(
            questionnaire_version=pending.version,
            content_type=ContentType.objects.get_for_model(type(self)),
            object_id=self.pk,
            target_label=self._meta.label_lower,
            target_key=self.edit_key(),
            action=pending.action,
            changes=pending.changes,
            acknowledged_by=pending.acknowledgement.user,
            reason=pending.acknowledgement.reason,
            responses_at_edit=pending.responses_at_edit,
        )
