# Vinta Django Questionnaires

A reusable Django application for building data-driven questionnaires.

[![PyPI](https://img.shields.io/pypi/v/vinta-django-questionnaires.svg)](https://pypi.org/project/vinta-django-questionnaires/)
[![CI](https://github.com/vintasoftware/vinta-django-questionnaires/actions/workflows/ci.yml/badge.svg)](https://github.com/vintasoftware/vinta-django-questionnaires/actions/workflows/ci.yml)

Supports Python 3.10, 3.11, 3.12, 3.13, 3.14 and Django 5.2, 6.0.


## Installation

```bash
pip install vinta-django-questionnaires
```

Then add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...,
    "vinta_django_questionnaires",
]
```


## Trying it

There is a runnable project under [example/](example/README.md) with a seeded
questionnaire -- four pages, conditions, a skippable page, a nested
sub-questionnaire, a model-backed value set and a couple of project-specific
validators:

```bash
uv run python -m example.manage migrate
uv run python -m example.manage seed_example
uv run python -m example.manage demo_response   # narrates a whole response
uv run python -m example.manage runserver       # admin at /admin/, API at /api/questionnaires/
```

And a React front end for it under [demo/](demo/README.md) -- TanStack Start,
Vite and the [vinta-schedule-design-system](https://www.npmjs.com/package/vinta-schedule-design-system),
rendering and validating entirely from the plan the server sends:

```bash
npm --prefix demo install
npm --prefix demo run dev   # http://localhost:5273, with Django on 8000
```


## Usage

### Defining a questionnaire

A questionnaire is a key with versions; everything else hangs off a version.

```python
from vinta_django_questionnaires.models import (
    Page,
    Question,
    Questionnaire,
    QuestionnaireVersion,
    Section,
)
from vinta_django_questionnaires.question_types import QuestionType

intake = Questionnaire.objects.create(key="intake")
version = QuestionnaireVersion.objects.create(questionnaire=intake, version=1, title="Intake form")
page = Page.objects.create(questionnaire_version=version, key="about", title="About you")
section = Section.objects.create(page=page, key="basics", title="Basics")
question = Question.objects.create(
    section=section,
    key="email",
    title="Email",
    question_type=QuestionType.FREE_TEXT,
)
```

Every model runs `full_clean()` on save, so a question can never reference a
widget that cannot render it, carry props its widget rejects, or name a
validator nobody registered. Pass `save(validate=False)` from data migrations.

Pages, sections and questions each take a `condition`: a JMESPath expression
evaluated against the answers. `version.iter_applicable_questions(answers)`
yields the questions that should actually be validated and saved.

### Changing a questionnaire that is already in use

Every page, section and question belongs to exactly one version. Nothing is
shared between versions, so a version that has been answered can never change
underneath those answers by accident.

The ordinary way to change a live questionnaire is therefore to fork it:

```python
from vinta_django_questionnaires.versioning import new_version_from

draft = new_version_from(version)  # a deep copy, as a new draft
draft.pages.get(key="about").sections.get(key="basics").questions.get(key="colour").delete()
draft.publish()
```

The copy carries everything -- window size ranges, the columns each layer sets,
pages, sections, questions, choices, validators -- and keeps question keys, so
answers stay comparable from one version to the next. What a question points
*at*, like a widget or a value set, is shared: those are their own records.

Editing in place is still allowed, because sometimes a typo is just a typo. But
once a version has responses, an edit to a page, section, question, choice or
validator changes what those responses mean, so it has to be acknowledged, and
the acknowledgement is kept:

```python
from vinta_django_questionnaires.editing import acknowledged_edit

with acknowledged_edit(user=request.user, reason="The old wording was ambiguous"):
    question.title = "What is your company's name?"
    question.save()
```

Without that, the save raises `UnacknowledgedEdit`. With it, an
`AcknowledgedEdit` row records who, when, why, what changed field by field, and
how many responses were already in when they did it.

The line is the first response: before that there is nothing to reinterpret, so
authors correct a live version freely. Override `requires_acknowledgement()` to
draw it elsewhere -- at publication, say.

What is gated is the models a respondent reads or is measured against: pages,
sections, questions, their choices and their validators. The responsive grid is
not -- `LayerColumns` and `QuestionMinimumColumns` are their own models, and
narrowing a question on a phone does not change what its answer meant. A
question's `order` *is* gated, because it is a field of the question.

The admin puts that in front of someone as a checkbox; see below.
`AcknowledgedEditAdminMixin` does the same for an admin of your own:

```python
@admin.register(Question)
class QuestionAdmin(AcknowledgedEditAdminMixin, admin.ModelAdmin):
    pass
```

### Telling whether a question is still the same question

Because versions copy rather than share, "is this the same question as in v1?"
needs an answer. Keys give identity; fingerprints give sameness:

```python
from vinta_django_questionnaires.fingerprints import compare_versions

comparison = compare_versions(version_1, version_3)
comparison.unchanged  # question keys that ask exactly the same thing
comparison.changed  # ... and those that do not
comparison.can_pool("email")  # whether answers to it are comparable
```

A fingerprint covers what a respondent reads or is measured against -- title,
description, type, choices, validators, condition -- and ignores presentation,
so reordering a form or swapping a widget leaves it alone.

### Validating answers

Validators are configured per question, in order, and each one receives a
context carrying what the earlier ones found.

```python
from vinta_django_questionnaires.models import QuestionValidator

QuestionValidator.objects.create(
    question=question,
    validator="required",
    order=0,
)
QuestionValidator.objects.create(
    question=question,
    validator="email",
    order=1,
    message_overrides={"invalid_email": "We need a working address."},
)

context = question.run_validators("not-an-email")
[issue.error_key for issue in context.issues]  # ["invalid_email"]
```

Other apps add their own from a `questionnaire_validators` module, which the
app config autodiscovers:

```python
from vinta_django_questionnaires.validators import BaseValidator, ClientSpec, register_validator


@register_validator
class IsCompanyDomainValidator(BaseValidator):
    key = "is_company_domain"
    error_messages = {"foreign_domain": "Use your {domain} address."}
    params_schema = {
        "type": "object",
        "properties": {"domain": {"type": "string"}},
        "required": ["domain"],
        "additionalProperties": False,
    }
    client = ClientSpec.custom()  # or ClientSpec.server_only()

    def validate(self, value, context):
        if not value.endswith(f"@{self.params['domain']}"):
            self.fail("foreign_domain", domain=self.params["domain"])
```

### Filling in a response

A response is filled a page at a time. Each page pushed becomes a
`PageResponse`, so which pages exist -- and the order they are in -- is what
says where the respondent got to.

```python
from vinta_django_questionnaires.submissions import skip_page, start_response, submit_page

response = start_response(version, respondent=request.user)
response.current_page  # the first page still pending
submit_page(response, page, {"email": "hugo@vinta.com.br"})
response.progress()  # completed / skipped / pending / current / isComplete
```

`submit_page` validates the page on its own and writes nothing if it does not
hold up, raising `PageValidationError` with the issues keyed by question. What
the page is asking is decided against the answers as they will be once the page
lands, so a question whose condition depends on an answer in the same payload
is handled.

A page marked `is_skippable` can be left for later:

```python
skip_page(response, page)  # recorded as skipped, reason "manual_action"
```

A page whose condition does not hold is recorded too, with the reason
`false_condition`, so every page of a response has an account of itself. The
difference matters: a manual skip is still pending -- skipping means later, not
never -- while a page ruled out by its condition is not, and does not hold up
completion.

Conditions depend on answers, and answers change. `sync_condition_skips` runs
after every submission and keeps those records honest: a page ruled out after
being filled becomes `false_condition` and its answers stop counting, and if
the condition holds again the page comes back with its answers intact.

### What a version still accepts

Each version decides for itself whether a recorded answer can be changed, and
until when:

```python
from datetime import datetime, timezone as tz

version.edit_policy = EditPolicy.ALWAYS  # never / until_completed / always
# After this, no page can be answered:
version.responses_due_at = datetime(2026, 9, 30, 23, 59, tzinfo=tz.utc)
# After this, no answer can be changed:
version.edits_due_at = datetime(2026, 10, 15, 23, 59, tzinfo=tz.utc)
version.save()
```

Answering and editing are different acts with their own deadline. Writing a
page that has nothing recorded yet is answering, governed by
`responses_due_at`. Writing one that already has answers is editing, governed
by `edit_policy` and `edits_due_at`. The two are independent, so a version can
stop taking new answers on Friday while letting the answers it has be
corrected until Sunday -- or the other way around.

`edit_policy` is a choice rather than a flag because "editable" means two
different things:

| Policy | What a respondent can change |
| --- | --- |
| `never` | Nothing. A page is final the moment it is recorded |
| `until_completed` | Pages already answered, while the response is in progress. The default, and what the package did before this field existed |
| `always` | Anything, including a response that was handed in |

Editing a completed response can make it incomplete again -- a changed answer
can bring a conditional page back into play -- so the status follows what is
recorded, and the response reopens on its own.

`start_response`, `submit_page` and `skip_page` enforce all of this, raising
`RespondingClosed`, `EditingClosed` or `EditingNotAllowed`.

### The response API

Include the views where you want them:

```python
urlpatterns = [
    path("api/questionnaires/", include("vinta_django_questionnaires.urls")),
]
```

| Endpoint | What it does |
| --- | --- |
| `POST` `responses/` | Open a response; returns the plan and where to start |
| `GET` `responses/{id}/` | Where the respondent is, and what to render |
| `POST` `responses/{id}/pages/{key}/` | Push one page's answers |
| `POST` `responses/{id}/pages/{key}/skip/` | Leave a page for later |

A page that does not validate comes back as `422`, with the issues keyed by
question:

```json
{"errors": {"email": [{"validator": "email", "errorKey": "invalid_email", "message": "..."}]}}
```

A page refused because the deadline passed or the version does not allow the
change comes back as `409` with a `detail`. Every response payload carries a
`policy` block -- `editPolicy`, `canRespond`, `canEdit`, `responsesDueAt`,
`editsDueAt` -- so the client can put the form in read-only rather than let
someone type into a page that will be refused.

Who may open a response, and who may see one, are methods on
`ResponseAccessMixin` rather than settings. The defaults are the careful ones:
authenticated users, each seeing only their own. Override `check_access`,
`get_respondent` or `get_response_queryset` for anonymous or externally
identified respondents.

### The admin

The package ships its own admin and registers it when the app is installed, so
there is nothing to write:

```python
INSTALLED_APPS = ["vinta_django_questionnaires", ...]
```

It is arranged around what someone actually does rather than around the model
graph, because the graph is four deep and following it means five page loads
and four saves to fix a typo.

- **A questionnaire** lists its versions, each with a link straight to its
  structure, its settings and its responses, and a button that starts the next
  version by copying the latest.
- **A version's change form** holds only what belongs to the version: title,
  status, the two deadlines, the breakpoints, the grid. Everything *in* it is
  one click away.
- **The structure editor** is the point. Every page, section, question, choice
  and validator of a version is on one form and saves together, so a change
  that touches six of them is one save. Rows carry the key, title and type;
  everything else is behind a disclosure, and each list reorders by dragging or
  with the arrow keys. The validator dropdown is the registry, so a validator
  another app registered is there without this package knowing about it.
- **The responses** have a table view with a column per question, a picker
  grouped by page, and a CSV export that takes exactly the columns on screen --
  the same `reporting` module the API and the React demo use, so the three
  cannot drift. Each response also shows what it wrote into your own models and
  what it set off, with a link to the record.

Editing a version that has responses asks for the acknowledgement once, for the
whole page, and records it against every change the save makes.

One thing to set. The structure editor posts a whole questionnaire in one form,
which for a dozen questions is a couple of thousand inputs, and Django's
`DATA_UPLOAD_MAX_NUMBER_FIELDS` defaults to 1000:

```python
DATA_UPLOAD_MAX_NUMBER_FIELDS = 5000
```

Without it the editor says so, with the number it needs, rather than failing
with a traceback.

#### Registering it yourself

Registering is opt-out, because a project may already have an admin for one of
these models, or may want a different base class under all of them:

```python
QUESTIONNAIRES_REGISTER_ADMIN = False
```

Then call `register()` from your own `admin.py`. It skips anything already
registered, so adding one admin of your own needs nothing else:

```python
from vinta_django_questionnaires.admin import register, unregister

register()  # everything not already registered
register(my_site)  # against a site of your own
register(force=True)  # replacing what is there
unregister()  # take it all back off
```

#### With a themed admin

A themed admin styles a form through the base class it is built on, so
`register()` takes the bases to put underneath -- inlines included, since those
are declared inside the admin classes. For
[django-unfold](https://unfoldadmin.com), that is the whole of it:

```python
from unfold.admin import ModelAdmin, TabularInline
from vinta_django_questionnaires.admin import register

register(model_admin_base=ModelAdmin, inline_base=TabularInline)
```

The structure editor and the response table are pages of ours rather than the
admin's, so they are styled from `static/vinta_django_questionnaires/admin.css`.
Every colour there is a `--vqa-` token mapped onto the Django admin's own, and
each mapping falls back to a value mixed out of `currentColor` -- so a theme
that defines none of Django's properties (Unfold defines not one of them) gets
borders and shading that read against whatever background it uses, rather than
the silent collapse an unguarded `var()` would cause.

Both are checked: the editor measures zero WCAG AA failures under Django's
light and dark themes and under Unfold's, and the whole flow -- editing across
three levels, the acknowledgement gate, saving -- was exercised under Unfold.

### The authoring API and the React editor

Questionnaires are edited in the Django admin, or from the React editor the
client package ships. The editor needs two things the response API does not
have -- a version as an editable document, and a catalog of what can be picked
-- so those live behind their own URLs:

```python
urlpatterns = [
    path("api/authoring/", include("vinta_django_questionnaires.editor_urls")),
]
```

| Endpoint | What it does |
| --- | --- |
| `GET` `catalog/` | The question types, validators, widgets and value sets there are |
| `GET` `questionnaires/` | What there is to edit |
| `POST` `questionnaires/new/` | A new questionnaire and its first draft |
| `DELETE` `questionnaires/{key}/` | Drop it, unless it has been answered |
| `GET` `questionnaires/{key}/versions/{n}/` | The version as an editable document |
| `PUT` `questionnaires/{key}/versions/{n}/` | Apply a document, all of it or none |
| `DELETE` `questionnaires/{key}/versions/{n}/` | Drop a draft, unless it has been answered |
| `POST` `questionnaires/{key}/versions/{n}/fork/` | Copy it into a new draft |

Who may author is `AuthoringAccessMixin.check_access`, and the default is staff
only.

The document is not the validation plan. The plan is resolved and flattened for
rendering; the document keeps every field as its author set it -- a column
count each layer *declares* rather than the one it resolves to, an empty widget
where the author left the type's default -- because that is what has to go
back.

```python
from vinta_django_questionnaires.definition import apply_definition, definition_document

document = definition_document(version)
document["pages"][0]["title"] = "About you"
apply_definition(version, document)
```

Keys are identity. A page, section, question or choice is matched to what is
stored by its key, so changing a key is a delete and a create rather than a
rename -- answers are keyed by question key, and pretending otherwise would
quietly reattach them to a different question. The editor says so before you
save.

A document that does not hold up is refused whole, with one entry per node that
would not go, addressed the way the editor addresses its own state:

```json
{"issues": [{"path": "pages.0.sections.0.questions.2", "errors": {"key": ["..."]}}]}
```

One bad question does not hide the other nine: every node is checked, and
nothing at all is written unless all of it was. Editing a version that already
has responses goes through the same acknowledgement gate as any other in-place
edit -- `PUT` takes `{"document": ..., "acknowledgement": {"understood": true,
"reason": "..."}}`, and without it the save is refused.

For the editor itself, see [client/README.md](client/README.md#the-editor).

### Reading the responses

The same authoring URLs serve the responses as a table. What the columns are is
not something a client can know in advance, so they come back with the rows --
one per question the version asks, in the order it asks them, plus the handful
of things about a response anyone reading a table wants.

| Endpoint | What it does |
| --- | --- |
| `GET` `responses/` | One page of rows, and every column there was to pick |
| `GET` `responses/export/` | The same table, filtered and columned the same way, as CSV |

Both take `questionnaire`, `version`, `status`, `search` and `columns`; the
listing adds `page` and `pageSize`. Filtering by questionnaire is what makes
answer columns available at all -- a table across every questionnaire has only
the metadata ones, because different questionnaires ask different things.

```python
from vinta_django_questionnaires.reporting import columns_for, csv_rows, response_queryset

columns = columns_for(version)
rows = csv_rows(response_queryset(questionnaire="intake"), columns)
```

The export is streamed, and the listing costs one query for the answers of the
whole page rather than one per row -- a table is exactly where that matters. An
answer with no flat form, a matrix or a list of files, goes into a CSV cell as
the JSON it already is.

### Turning a response into something else

Two things a project almost always wants once a response is in: put the answers
into its own models, and tell another system about them. Both are configured
rather than coded, and both read the answers the way conditions do -- JMESPath,
one expression per field.

**A mapping** names its target through the content type framework, so this
package never has to know about the model it writes to:

```python
mapping = ResponseMapping.objects.create(
    key="onboarding-lead",
    name="Onboarding to Lead",
    questionnaire=questionnaire,
    content_type=ContentType.objects.get_for_model(Lead),
    operation=MappingOperation.UPSERT,
    defaults={"source": "client-onboarding"},
)
MappingField.objects.create(
    mapping=mapping,
    role=FieldRole.LOOKUP,
    target_field="email",
    expression="answers.email",
    is_required=True,
)
MappingField.objects.create(
    mapping=mapping,
    target_field="company",
    expression="answers.company_name",
)
```

`insert` creates; `update` writes to whatever the lookup fields find, and does
nothing when they find nothing; `upsert` does one or the other. `defaults` are
written when a record is created, and a mapped field with a value of its own
wins over them. A lookup that resolves to nothing is skipped rather than
matching every row, an unanswered optional field is left out rather than
nulling what is there, and a required one that resolves to nothing abandons the
whole mapping.

**A webhook** is three templates over the same document -- the URL, the headers
and the body:

```python
ResponseWebhook.objects.create(
    key="onboarding-crm",
    questionnaire=questionnaire,
    method="POST",
    url_template="https://crm.example.com/companies/{company}/leads/",
    url_params={"company": "answers.company_name"},
    headers={"X-Response": {"$jmespath": "id"}},
    body={"email": {"$jmespath": "answers.email"}, "source": "questionnaire"},
)
```

Anywhere in the headers or the body, `{"$jmespath": "..."}` is replaced by what
that expression resolves to; everything else is a literal. A `{placeholder}` in
the URL needs an expression in `url_params`, which is checked on save rather
than discovered at delivery.

Both run when the response completes, or on every page if `trigger` says so, and
both carry a `condition` of their own. Neither can break a submission: they run
after the transaction commits, each outcome is written down as a `MappingRun` or
a `WebhookDelivery`, and the respondent never sees a failure. The document they
read is the answers, flat and under `answers`, plus the response's own metadata:

```python
{
    "email": "...",
    "answers": {"email": "..."},
    "id": "...",
    "status": "completed",
    "questionnaire": "intake",
    "version": 2,
    "context": {},
    "respondent": {...},
}
```

Delivery goes through the standard library, so there is no new dependency. Point
`QUESTIONNAIRES_WEBHOOK_SENDER` at a `send(request)` of your own to use
something else, and set `QUESTIONNAIRES_RUN_INTEGRATIONS = False` to stop the
submission layer running them inline and call `run_integrations()` from a task
queue instead.

### The API, written down

[`openapi.yml`](openapi.yml) describes both URL modules -- every path, method,
parameter and payload. The test suite checks it against the URLconf, so an
endpoint added without a matching entry fails CI rather than going unnoticed.

### The same rules in the browser

`vinta_django_questionnaires.plan` emits a JSON validation plan -- base type,
checks in order, resolved messages -- that the TypeScript client turns into a
Zod schema. See [client/README.md](client/README.md).

```python
from vinta_django_questionnaires.plan import questionnaire_plan

return JsonResponse(questionnaire_plan(version))
```

Both sides replay `shared/conformance-cases.json`, so a rule that behaves
differently in the browser than on the server fails CI.


## Development

The project uses [uv](https://docs.astral.sh/uv/) for dependency management and
[tox](https://tox.wiki/) to run the suite across the support matrix.

```bash
uv sync --all-groups
uv run pre-commit install --install-hooks --hook-type commit-msg
uv run pytest
```

Useful commands:

| Command | What it does |
| --- | --- |
| `uv run pytest` | Run the test suite on the current interpreter |
| `uv run tox` | Run it on every supported Python and Django |
| `uv run tox -e lint` | Check formatting and lint rules |
| `uv run tox -e types` | Type check with mypy and django-stubs |
| `uv run tox -e build` | Build the sdist and wheel and check the metadata |
| `uv run python -m tests.manage makemigrations` | Generate migrations for the app |
| `uv run python -m tests.manage dump_validation_manifest --output shared/validators.json` | Refresh the validator manifest |
| `uv run python -m tests.manage dump_conformance_cases --output shared/conformance-cases.json` | Refresh the conformance corpus |
| `npm --prefix client test` | Replay that corpus against the TypeScript client |

Both `shared/` artifacts are checked into the repository and asserted to be
current by the test suite: adding or changing a validator means regenerating
them in the same commit.

## Releasing

Both packages share a version and go out together, on one `vX.Y.Z` tag. CI
refuses a commit where `pyproject.toml` and `client/package.json` disagree, so
the tag can only ever mean one thing.

1. Bump the version in **both** `pyproject.toml` and `client/package.json`, and
   move the `Unreleased` section of `CHANGELOG.md` under the new number.
2. Tag the commit as `vX.Y.Z` and publish a GitHub release.
3. `publish.yml` builds the Django app, checks the tag against the version, and
   uploads to PyPI. `publish-client.yml` type checks, tests and builds the
   client, checks the tag against the version and that the version is not
   already on npm, and publishes it.

The Django app is republished even when nothing in it changed; that is the cost
of a shared version, and it is cheaper than two numbers to keep track of.

To rehearse: run `publish.yml` manually with the `testpypi` target, and
`publish-client.yml` manually with **Dry run** ticked -- the latter does
everything up to `npm pack` and keeps the tarball as an artifact.

Neither workflow stores a token. Both mint a short-lived one from GitHub's OIDC,
which is why each has its own deployment environment -- `pypi`, `testpypi` and
`npm` -- named in the trusted publisher on the other side. npm's provenance
attestation is generated from the same exchange, and is why
`client/package.json` carries a `repository` field pointing at this repository
and the `client` directory inside it.

## Staying up to date with the template

This project was generated from
[vinta-django-package](https://github.com/vintasoftware/vinta-django-package).
To pull in later improvements to the tooling:

```bash
uvx copier update --trust
```


## License

MIT. See [LICENSE](LICENSE).
