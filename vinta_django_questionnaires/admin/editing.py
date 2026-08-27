"""Editing a live definition from the admin, on the record.

Once a version has responses, changing what a question asks changes what those
answers mean.  These are what put that in front of someone as a checkbox rather
than letting it happen quietly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from django.contrib import admin  # noqa: TC002  -- a base class, not just a type

from vinta_django_questionnaires.editing import acknowledged_edit
from vinta_django_questionnaires.forms import AcknowledgedEditForm

if TYPE_CHECKING:
    # A mixin is not a `ModelAdmin`, but it only makes sense on one, and saying
    # so is what lets a type checker see that `super().save_model` exists and
    # that `form` is the same attribute the admin already has.
    from django.contrib.admin.options import InlineModelAdmin
    from django.http import HttpRequest

    AdminBase: TypeAlias = admin.ModelAdmin[Any]
    InlineBase: TypeAlias = InlineModelAdmin[Any, Any]
else:
    AdminBase = object
    InlineBase = object


def signed_form(form_class: Any, user: Any) -> Any:
    """A form class that knows who is filling it in."""

    class SignedForm(form_class):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("acknowledged_by", user)
            super().__init__(*args, **kwargs)

    return SignedForm


class AcknowledgedEditInlineMixin(InlineBase):
    """The same box, on an inline row.

    Mix into a ``TabularInline`` or ``StackedInline`` over a gated model, so a
    question's choices and validators can be edited from the question itself.
    """

    form = AcknowledgedEditForm

    def get_formset(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> Any:
        formset = super().get_formset(request, obj, **kwargs)
        formset.form = signed_form(formset.form, request.user)
        return formset


class AcknowledgedEditAdminMixin(AdminBase):
    """Puts the acknowledgement box on a ModelAdmin, and signs the record.

    Mix into the admin of a page, section, question, choice or validator::

        @admin.register(Question)
        class QuestionAdmin(AcknowledgedEditAdminMixin, admin.ModelAdmin):
            pass

    Deleting is withdrawn rather than gated: an unacknowledged delete would
    only fail at the last moment, and there is no box on the confirmation page
    to tick.  Delete such a row in code, inside ``acknowledged_edit``.
    """

    form = AcknowledgedEditForm

    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> Any:
        return signed_form(super().get_form(request, obj, change=change, **kwargs), request.user)

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        reason = form.cleaned_data.get("edit_reason", "") if hasattr(form, "cleaned_data") else ""
        if getattr(form, "cleaned_data", {}).get("understood"):
            with acknowledged_edit(user=request.user, reason=reason):
                super().save_model(request, obj, form, change)
            return
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and obj.requires_acknowledgement():
            return False
        return bool(super().has_delete_permission(request, obj))


__all__ = ["AcknowledgedEditAdminMixin", "AcknowledgedEditInlineMixin", "signed_form"]
