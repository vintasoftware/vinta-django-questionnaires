"""Which scopes a read is allowed to see.

Every function in this package that builds a queryset over responses takes one
of these, and takes it as a **required** keyword argument.  That is deliberate:
a boundary that defaults to open is the failure this exists to prevent, so an
installation with a single tenant writes ``ScopeFilter.everything()`` once, at
the call site, where it can be read and grepped for.

Two spellings, because the two questions are different:

``ScopeFilter.only("acme")``
    What belongs to this tenant.  Used for responses -- a response is always
    somebody's, never the installation's.

``ScopeFilter.only("acme", include_global=True)``
    What this tenant may *use*.  Used for definitions -- a questionnaire the
    whole installation shares is answerable by every tenant, so it has to show
    up alongside the tenant's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

    _M = TypeVar("_M", bound=Model)

#: The global scope's key.  Empty rather than a sentinel word so that no tenant
#: key can ever collide with it: a scope with a value is never blank.
GLOBAL_SCOPE_KEY = ""


@dataclass(frozen=True)
class ScopeFilter:
    """The scopes a read may see.

    ``keys is None`` means every scope, which is what a single-tenant
    installation and the staff admin both want.  It is spelled
    :meth:`everything` rather than left as the default so that "all tenants" is
    always a decision somebody wrote down.
    """

    keys: tuple[str, ...] | None = None
    include_global: bool = False

    @classmethod
    def everything(cls) -> ScopeFilter:
        """Every scope, global and tenant alike."""
        return cls(keys=None)

    @classmethod
    def only(cls, *keys: str, include_global: bool = False) -> ScopeFilter:
        """Just these scopes, and optionally what the installation shares."""
        return cls(keys=tuple(keys), include_global=include_global)

    @property
    def is_everything(self) -> bool:
        return self.keys is None

    def matching_keys(self) -> tuple[str, ...]:
        """The keys this filter accepts, sorted, or ``()`` when unrestricted."""
        if self.keys is None:
            return ()
        found = set(self.keys)
        if self.include_global:
            found.add(GLOBAL_SCOPE_KEY)
        return tuple(sorted(found))

    def apply(self, queryset: QuerySet[_M], *, field: str = "scope_key") -> QuerySet[_M]:
        """Narrow *queryset* to this filter.

        *field* is the lookup reaching the scope key: ``"scope_key"`` on a
        response, which carries its own copy, and ``"scope__scope_key"``
        anywhere else.

        An empty :meth:`only` -- no keys and no global -- filters everything
        out rather than letting everything through, which is the safe reading
        of "these scopes, of which there are none".
        """
        if self.keys is None:
            return queryset
        return queryset.filter(**{f"{field}__in": self.matching_keys()})


__all__ = ["GLOBAL_SCOPE_KEY", "ScopeFilter"]
