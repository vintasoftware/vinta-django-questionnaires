"""What a questionnaire and a response belong to.

A scope is the tenant boundary: an organization, a workspace, an account, or
the installation at large.  Projects disagree about what that *is*, so the
model is swappable the way ``AUTH_USER_MODEL`` is -- point
``QUESTIONNAIRES_SCOPE_MODEL`` at your own subclass and it gets a foreign key
to your organization, a label, and whatever else belongs on a tenant row.

``scope_key`` is the portable spelling of a scope: a string that indexes
cheaply, reads without a join, and means the same thing in an export as it does
in the database.  It must be **stable for the life of the scope** -- rows are
found by it.  A primary key is a good key; a renameable slug is not.

A scope is never *changed* once set.  ``ScopedModel`` is what enforces that,
and the immutability is load-bearing rather than tidy: it is why the
``scope_key`` copied onto a response cannot drift from the foreign key beside
it, and why nothing here needs the careful ``update_fields`` repair that a
mutable scope would demand.
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from vinta_django_questionnaires import conf
from vinta_django_questionnaires.models.base import BaseModel

#: The model the foreign keys below point at, resolved at import time because a
#: field definition needs a target now.  It defaults to the model this package
#: ships, so an installation that has not overridden it still works -- the
#: swappable machinery reads the same setting and simply finds nothing to swap.
SCOPE_MODEL = conf.get(conf.SCOPE_MODEL, conf.DEFAULT_SCOPE_MODEL)

#: What a subclass says a scope *is*.  Spelled the old way rather than with
#: PEP 695 syntax because this package still supports Python 3.10.
ScopeValue = TypeVar("ScopeValue")


class ScopeType(models.TextChoices):
    """Whether something belongs to one tenant or to the installation at large.

    ``GLOBAL`` is for a questionnaire the whole installation shares -- a
    platform-wide survey every tenant's respondents answer.  ``SCOPED`` is
    everything that belongs inside one tenant, workspace or account, whatever
    the installing project calls its boundary.
    """

    GLOBAL = "global", _("Global")
    SCOPED = "scoped", _("Scoped")


class AbstractQuestionnaireScope(BaseModel, Generic[ScopeValue]):
    """The tenant boundary, with the one rule that holds whatever it is.

    Subclasses decide what a scope *is* by implementing the ``scope`` property
    over whatever columns suit them -- a foreign key, a string, a composite --
    while this class owns the invariant that holds whatever they choose:
    ``scope_type`` and ``scope`` agree, always.
    """

    scope_type = models.CharField(
        _("scope type"),
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.GLOBAL,
    )
    scope_key = models.CharField(
        _("scope key"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_("Stable string form of this scope. Never changes once records reference it."),
    )
    label = models.CharField(_("label"), max_length=255, blank=True, default="")

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return self.label or self.scope_key or str(ScopeType(self.scope_type).label)

    # -- what a scope is ---------------------------------------------------
    @property
    def scope(self) -> ScopeValue | None:
        """The thing this scope names, or ``None`` for the global scope."""
        raise NotImplementedError("Subclasses decide what a scope is.")

    def build_scope_key(self) -> str:
        """The portable string form of this scope, ``""`` when global.

        Must be stable for the life of the scope and unique among scopes of the
        same type: responses are found by this value, so a key that changes
        detaches every row already written under the old one.
        """
        raise NotImplementedError("Subclasses decide what a scope is.")

    # -- the invariant -----------------------------------------------------
    def validate_scope(self) -> None:
        """Reject a row whose scope value and scope type disagree.

        Checked against the *final* state rather than against what changed, so
        insert and update run the identical rule and a partial update cannot
        slip a mismatch through by touching only one of the two.

        This is a convenience check, not the guarantee: ``save`` is bypassed by
        ``bulk_create`` and ``QuerySet.update``, so concrete subclasses are
        expected to carry a check constraint saying the same thing.
        """
        is_global = self.scope_type == ScopeType.GLOBAL
        if is_global is not (self.scope is None):
            raise ValidationError(
                {"scope_type": _("The scope type and the scope value do not agree.")}
            )

    def clean(self) -> None:
        super().clean()
        self.validate_scope()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.scope_key = self.build_scope_key()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "scope_key" not in update_fields:
            # A partial update that moves the scope but leaves ``scope_key``
            # behind would silently detach the scope from its own responses, so
            # add the column rather than let the write proceed.
            kwargs["update_fields"] = [*update_fields, "scope_key"]
        super().save(*args, **kwargs)


class QuestionnaireScope(AbstractQuestionnaireScope[str]):
    """The scope model this package ships: an opaque string.

    Enough for a project with no tenant concept, which is why it is the default
    the swappable setting points at -- installing this package does not require
    thinking about scopes at all.  A project with a real boundary points
    ``QUESTIONNAIRES_SCOPE_MODEL`` at its own subclass instead.
    """

    # Underscore-prefixed because ``scope`` itself is the property above; this
    # is the column behind it.  Non-nullable, with "" as the absent value -- an
    # empty string participates in constraints and indexes where NULL does not.
    _scope = models.CharField(_("scope"), max_length=255, blank=True, default="")

    class Meta:
        verbose_name = _("questionnaire scope")
        verbose_name_plural = _("questionnaire scopes")
        ordering = ["scope_type", "scope_key"]
        swappable = "QUESTIONNAIRES_SCOPE_MODEL"
        constraints: ClassVar = [
            # The invariant ``validate_scope`` checks, held where ``save``
            # cannot reach: ``bulk_create`` and ``QuerySet.update`` never call it.
            models.CheckConstraint(
                condition=(
                    models.Q(scope_type=ScopeType.GLOBAL, _scope="")
                    | (~models.Q(scope_type=ScopeType.GLOBAL) & ~models.Q(_scope=""))
                ),
                name="questionnaire_scope_type_and_value_agree",
            ),
            models.UniqueConstraint(
                fields=["scope_type", "scope_key"],
                name="questionnaire_scope_unique_key_per_type",
            ),
        ]

    @property
    def scope(self) -> str | None:
        return self._scope or None

    @scope.setter
    def scope(self, value: str | None) -> None:
        self._scope = value or ""
        self.scope_type = ScopeType.GLOBAL if not value else ScopeType.SCOPED

    def build_scope_key(self) -> str:
        return self._scope


class ScopedModel(models.Model):
    """A model that belongs to a scope, set once and never afterwards.

    The scope defaults to the global one, which is what keeps every existing
    caller working: ``Questionnaire.objects.create(key="intake")`` still does
    what it always did, in an installation that has one scope.
    """

    scope = models.ForeignKey(
        SCOPE_MODEL,
        # Deleting a tenant must not delete the questionnaires and answers
        # collected inside it.
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name=_("scope"),
    )

    #: The scope this row was loaded with, so ``clean`` can refuse a change.
    #: ``None`` on an unsaved instance, which is what makes the first save free.
    _loaded_scope_id: Any = None

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        # ``getattr`` rather than ``self.scope_id``: the column is NOT NULL,
        # so django-stubs types the attribute as non-optional -- true of a
        # saved row, and not of the one being assembled here.
        if getattr(self, "scope_id", None) is None:
            self.scope = get_global_scope()
        super().save(*args, **kwargs)
        # Remember what was written.  Without this, an instance that came from
        # ``objects.create()`` rather than from the database would have no
        # loaded value to compare against, and the *next* save on that same
        # object could move the scope unchecked.
        self._loaded_scope_id = self.scope_id

    @classmethod
    def from_db(cls, *args: Any, **kwargs: Any) -> Any:
        # Deliberately signature-agnostic: Django 6.1 added a ``fetch_mode``
        # argument here, and this package is tested from 5.2 to main.
        instance = super().from_db(*args, **kwargs)
        instance._loaded_scope_id = instance.scope_id
        return instance

    def clean(self) -> None:
        """Refuse a scope that has moved.

        ``ValidatedModel`` runs ``full_clean()`` on every save, so this needs no
        call site of its own.  The honest limit is the one that applies to every
        model-level rule in Django: ``QuerySet.update()`` and ``bulk_update()``
        never call ``save()``, and because this compares against the *old* row
        no check constraint can express it.  Real teeth would mean a database
        trigger, which is not worth a dependency for a column nothing in this
        package writes after creation.
        """
        super().clean()
        loaded = getattr(self, "_loaded_scope_id", None)
        if loaded is not None and loaded != self.scope_id:
            raise ValidationError(
                {"scope": _("A scope cannot be changed. Copy this into the other scope instead.")}
            )


def get_global_scope() -> Any:
    """The scope standing for "the whole installation", made if it is missing.

    Every well-formed scope model can express this row: the invariant says a
    global scope has no value behind it, so whatever columns a project adds to
    identify a tenant have to be nullable anyway.
    """
    from vinta_django_questionnaires.models_registry import get_scope_model

    model = get_scope_model()
    scope, _created = model._default_manager.get_or_create(scope_type=ScopeType.GLOBAL)
    return scope


__all__ = [
    "SCOPE_MODEL",
    "AbstractQuestionnaireScope",
    "QuestionnaireScope",
    "ScopeType",
    "ScopedModel",
    "get_global_scope",
]
