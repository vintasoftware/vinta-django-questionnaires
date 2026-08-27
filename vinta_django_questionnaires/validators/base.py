"""The contract every validator implements, on both sides of the wire.

A validator is one link of a question's validation chain.  It declares the
error keys it can report, the params it accepts, and -- through
``ClientSpec`` -- how it is expressed in the browser: as native Zod checks, as
a custom implementation the client registers under the same key, or as
something only the server can decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

from vinta_django_questionnaires.schemas import validate_against_schema

if TYPE_CHECKING:
    from collections.abc import Mapping

    from django.utils.functional import Promise

    from vinta_django_questionnaires.models import Question

#: The validator maps onto native Zod checks.
CLIENT_MODE_CHECKS = "checks"
#: The client must register an implementation under the same key.
CLIENT_MODE_CUSTOM = "custom"
#: Only the server can run it; the client shows it as checked on submit.
CLIENT_MODE_SERVER_ONLY = "server_only"


@dataclass(frozen=True)
class Check:
    """One native check emitted to the client.

    ``args`` names the params, in order, that become the check's arguments:
    ``Check("string.min", args=("minimum",))`` on a validator configured with
    ``{"minimum": 3}`` emits ``{"kind": "string.min", "args": [3]}``.
    """

    kind: str
    error_key: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClientSpec:
    """How a validator crosses over to the browser."""

    mode: str = CLIENT_MODE_CUSTOM
    checks: tuple[Check, ...] = ()

    @classmethod
    def native(cls, *checks: Check) -> ClientSpec:
        return cls(mode=CLIENT_MODE_CHECKS, checks=checks)

    @classmethod
    def custom(cls) -> ClientSpec:
        return cls(mode=CLIENT_MODE_CUSTOM)

    @classmethod
    def server_only(cls) -> ClientSpec:
        return cls(mode=CLIENT_MODE_SERVER_ONLY)


@dataclass(frozen=True)
class Case:
    """One conformance case: the same input, checked on both sides.

    Cases live next to the validator they exercise.  The Python suite replays
    them against ``validate()``, and ``dump_conformance_cases`` writes them out
    with the emitted client checks so the TypeScript suite can replay the very
    same expectations against the Zod schema it builds.
    """

    value: Any
    params: dict[str, Any] = field(default_factory=dict)
    #: The error keys expected, in order.  Empty means the value is accepted.
    expects: tuple[str, ...] = ()
    question_type: str = ""
    label: str = ""


class ValidatorFailure(Exception):
    """Raised by a validator to report one of its declared error keys."""

    def __init__(self, error_key: str, **params: Any) -> None:
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params


@dataclass(frozen=True)
class ValidationIssue:
    """One failure, already resolved to the message the client should show."""

    validator: str
    error_key: str
    message: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidatorOutcome:
    """What one link of the chain produced, kept for the links after it."""

    validator: str
    value: Any
    issues: list[ValidationIssue] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass
class ValidatorOutput:
    """Returned by ``validate()`` to hand something to the next validator."""

    value: Any = None
    data: dict[str, Any] = field(default_factory=dict)


class ValidationContext:
    """The second argument every validator receives.

    It carries the question being validated, the whole answer set -- so
    validators can look at sibling questions -- and the outcome of every
    validator that already ran for this question.
    """

    def __init__(
        self,
        *,
        question: Question | None = None,
        answers: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        self.question = question
        self.answers: dict[str, Any] = dict(answers or {})
        self.extra: dict[str, Any] = dict(extra or {})
        self.outcomes: list[ValidatorOutcome] = []

    def record(self, outcome: ValidatorOutcome) -> None:
        self.outcomes.append(outcome)

    def outcome_for(self, validator_key: str) -> ValidatorOutcome | None:
        """The most recent outcome of *validator_key*, if it already ran."""
        for outcome in reversed(self.outcomes):
            if outcome.validator == validator_key:
                return outcome
        return None

    def data_for(self, validator_key: str) -> dict[str, Any]:
        outcome = self.outcome_for(validator_key)
        return outcome.data if outcome else {}

    @property
    def issues(self) -> list[ValidationIssue]:
        return [issue for outcome in self.outcomes for issue in outcome.issues]

    @property
    def is_valid(self) -> bool:
        return not self.issues


class BaseValidator:
    """Subclass this, declare ``key`` and ``error_messages``, implement ``validate``."""

    #: The key questions store to reference this validator, shared with the
    #: client implementation registered under the same string.
    key: ClassVar[str] = ""
    label: ClassVar[Promise | str] = ""
    #: Every error key this validator can report, with its default message.
    #: Messages are formatted with ``str.format`` against the failure params.
    error_messages: ClassVar[Mapping[str, Promise | str]] = {}
    #: JSON Schema for the ``params`` a question configures the validator with.
    params_schema: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    #: ``None`` means "every question type".
    supported_question_types: ClassVar[frozenset[str] | None] = None
    #: Whether an empty answer skips this validator, the way Zod skips checks
    #: on optional values.  ``required``-style validators set this to ``False``.
    skip_when_empty: ClassVar[bool] = True
    #: How this validator is expressed in the browser.  The default is the
    #: careful one: the client has to provide an implementation for it.
    client: ClassVar[ClientSpec] = ClientSpec(mode=CLIENT_MODE_CUSTOM)
    #: Whether ``validate()`` reads outcomes of earlier validators.  A chain
    #: containing one of these runs in chain mode on the client too.
    reads_context: ClassVar[bool] = False
    #: Conformance cases, replayed by both test suites.
    conformance: ClassVar[tuple[Case, ...]] = ()

    def __init__(
        self,
        params: Mapping[str, Any] | None = None,
        message_overrides: Mapping[str, str] | None = None,
    ) -> None:
        self.params: dict[str, Any] = dict(params or {})
        self.message_overrides: dict[str, str] = dict(message_overrides or {})

    def __repr__(self) -> str:
        return f"<{type(self).__name__} key={self.key!r} params={self.params!r}>"

    # -- declaration -------------------------------------------------------
    @classmethod
    def error_keys(cls) -> frozenset[str]:
        return frozenset(cls.error_messages)

    @classmethod
    def supports_question_type(cls, question_type: str) -> bool:
        return (
            cls.supported_question_types is None or question_type in cls.supported_question_types
        )

    @classmethod
    def check_params(cls, params: Any) -> None:
        """Raise ``ValidationError`` unless *params* match ``params_schema``."""
        validate_against_schema(params, dict(cls.params_schema))

    # -- the wire ----------------------------------------------------------
    def client_checks(self) -> list[dict[str, Any]]:
        """The checks the client should apply for this configuration.

        Override for a validator whose client shape depends on its params --
        ``min_value`` picking ``number.gt`` over ``number.gte``, say.
        """
        spec = self.client
        if spec.mode == CLIENT_MODE_CHECKS:
            return [
                self.emit_check(check.kind, check.error_key, self.check_args(check))
                for check in spec.checks
            ]
        return [
            {
                "kind": "custom",
                "validator": self.key,
                "params": dict(self.params),
                "messages": {
                    error_key: str(
                        self.message_overrides.get(error_key) or self.error_messages[error_key]
                    )
                    for error_key in self.error_messages
                },
                "serverOnly": spec.mode == CLIENT_MODE_SERVER_ONLY,
                "skipWhenEmpty": self.skip_when_empty,
            }
        ]

    def check_args(self, check: Check) -> list[Any]:
        return [self.params[name] for name in check.args]

    def emit_check(self, kind: str, error_key: str, args: list[Any]) -> dict[str, Any]:
        """One check on the wire.

        The message keeps whatever placeholders only the failure can fill --
        a file name, the offending entry -- and travels with the params, so the
        client formats it exactly the way ``message_for()`` does here.
        """
        return {
            "kind": kind,
            "validator": self.key,
            "args": args,
            "errorKey": error_key,
            "params": dict(self.params),
            "message": str(
                self.message_overrides.get(error_key) or self.error_messages.get(error_key, "")
            ),
            "skipWhenEmpty": self.skip_when_empty,
        }

    # -- execution ---------------------------------------------------------
    @staticmethod
    def is_empty(value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    def message_for(self, error_key: str, params: Mapping[str, Any]) -> str:
        template = self.message_overrides.get(error_key) or self.error_messages.get(error_key, "")
        try:
            return str(template).format(**params)
        except (IndexError, KeyError):
            return str(template)

    def fail(self, error_key: str, **params: Any) -> NoReturn:
        """Report *error_key* and stop this validator."""
        if error_key not in self.error_messages:
            raise KeyError(f"{type(self).__name__} does not declare the error key {error_key!r}")
        raise ValidatorFailure(error_key, **params)

    def validate(self, value: Any, context: ValidationContext) -> ValidatorOutput | None:
        """Check *value*, calling ``self.fail()`` when it does not hold up.

        Return a ``ValidatorOutput`` to hand a coerced value or extra data to
        the validators further down the chain.
        """
        raise NotImplementedError

    def run(self, value: Any, context: ValidationContext) -> ValidatorOutcome:
        """Run this validator and record the outcome on *context*."""
        outcome = ValidatorOutcome(validator=self.key, value=value)
        if self.skip_when_empty and self.is_empty(value):
            context.record(outcome)
            return outcome
        try:
            output = self.validate(value, context)
        except ValidatorFailure as failure:
            params = {**self.params, **failure.params, "value": value}
            outcome.issues.append(
                ValidationIssue(
                    validator=self.key,
                    error_key=failure.error_key,
                    message=self.message_for(failure.error_key, params),
                    params=failure.params,
                )
            )
        else:
            if output is not None:
                outcome.value = output.value if output.value is not None else value
                outcome.data = output.data
        context.record(outcome)
        return outcome
