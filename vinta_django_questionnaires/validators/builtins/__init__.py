"""The built-in validator library.

Importing this package registers every validator below.  They are grouped by
what they operate on rather than by which Zod check they map to, because that
is how someone building a questionnaire looks for them.
"""

from __future__ import annotations

from vinta_django_questionnaires.validators.builtins import (
    files,
    logic,
    numbers,
    presence,
    sequences,
    strings,
    temporal,
)

__all__ = ["files", "logic", "numbers", "presence", "sequences", "strings", "temporal"]
