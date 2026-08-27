"""The box someone ticks to edit a live definition in place."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires.editing import Acknowledgement, acknowledged_edit


class AcknowledgedEditForm(forms.ModelForm):  # type: ignore[type-arg]
    """A model form for a page, section, question, choice or validator.

    When the version already has responses, the form will not save until
    someone has said they understand what the edit does to them, and what they
    said is written down alongside the change.
    """

    understood = forms.BooleanField(
        required=False,
        label=_("I understand this changes what existing responses mean"),
        help_text=_("Editing a live questionnaire in place is recorded, with what changed."),
    )
    edit_reason = forms.CharField(
        required=False,
        label=_("Reason"),
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Kept with the record of this edit."),
    )

    def __init__(self, *args: Any, acknowledged_by: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.acknowledged_by = acknowledged_by

    def needs_acknowledgement(self) -> bool:
        return bool(self.instance and self.instance.requires_acknowledgement())

    def clean(self) -> dict[str, Any]:
        cleaned: dict[str, Any] = super().clean() or {}
        if self.needs_acknowledgement() and not cleaned.get("understood"):
            raise ValidationError(
                {
                    "understood": _(
                        "This version already has responses. Tick the box to record that you "
                        "mean to change what they mean, or make the change in a new version."
                    )
                }
            )
        return cleaned

    def _post_clean(self) -> None:
        # The model validates itself here, and it gates unacknowledged edits
        # too -- so the acknowledgement has to be in force already, not just by
        # the time save() runs.
        # django-stubs does not declare _post_clean, though every ModelForm has it.
        acknowledgement = self.acknowledgement()
        if acknowledgement is None:
            super()._post_clean()  # type: ignore[misc]
            return
        with acknowledged_edit(user=acknowledgement.user, reason=acknowledgement.reason):
            super()._post_clean()  # type: ignore[misc]

    def acknowledgement(self) -> Acknowledgement | None:
        if not getattr(self, "cleaned_data", {}).get("understood"):
            return None
        return Acknowledgement(
            understood=True,
            user=self.acknowledged_by,
            reason=self.cleaned_data.get("edit_reason", ""),
        )

    def save(self, commit: bool = True) -> Any:
        acknowledgement = self.acknowledgement()
        if acknowledgement is None:
            return super().save(commit)
        with acknowledged_edit(user=acknowledgement.user, reason=acknowledgement.reason):
            return super().save(commit)


__all__ = ["AcknowledgedEditForm"]
