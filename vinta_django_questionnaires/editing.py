"""Acknowledging an edit that changes what existing responses mean.

Editing a page, section or question in place is allowed.  Once a version has
responses, though, it stops being a private matter: an answer recorded against
"Do you have a company?" means something else if the question becomes "Do you
own a company?".  So the edit goes through, and the fact that someone chose to
make it is written down.

The acknowledgement travels through a context manager rather than an argument,
so it works the same for a form, the admin, a management command or a
migration::

    with acknowledged_edit(user=request.user, reason="Fixed a typo"):
        question.title = "What is your company's name?"
        question.save()
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True)
class Acknowledgement:
    """Someone saying they know what this edit does to existing responses."""

    #: The box.  An acknowledgement that does not claim understanding is not one.
    understood: bool = True
    user: Any = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.understood


_current: ContextVar[Acknowledgement | None] = ContextVar(
    "vinta_django_questionnaires_acknowledgement", default=None
)


class UnacknowledgedEdit(ValidationError):
    """Raised when an edit that needs acknowledging does not have one."""

    def __init__(self, instance: Any) -> None:
        super().__init__(
            _(
                "%(model)s belongs to a version that already has responses. Editing it in "
                "place changes what those responses mean. Create a new version, or "
                "acknowledge the edit to record that this was deliberate."
            ),
            code="unacknowledged_edit",
            params={"model": type(instance)._meta.verbose_name},
        )
        self.instance = instance


@contextmanager
def acknowledged_edit(
    *, user: Any = None, reason: str = "", understood: bool = True
) -> Iterator[Acknowledgement]:
    """Acknowledge every gated edit made inside the block."""
    acknowledgement = Acknowledgement(understood=understood, user=user, reason=reason)
    token = _current.set(acknowledgement)
    try:
        yield acknowledgement
    finally:
        _current.reset(token)


def current_acknowledgement() -> Acknowledgement | None:
    """The acknowledgement in force, if any."""
    return _current.get()
