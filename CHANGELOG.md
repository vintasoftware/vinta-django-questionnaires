# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]

### Added

- Initial project scaffolding.
- Questionnaire definition models: versioned questionnaires, pages, sections,
  questions, inline choices, value sets, widgets and the responsive column
  grid, with conditions evaluated through JMESPath.
- A dynamic validation layer: a validator registry other apps extend with
  `@register_validator`, and 24 built-in validators covering presence, text,
  numbers, dates and ranges, collections, files and cross-field predicates.
- A validation plan emitted per question or questionnaire version, and the
  `dump_validation_manifest` and `dump_conformance_cases` commands that write
  the artifacts under `shared/`.
- `@vintasoftware/django-questionnaires`, the TypeScript client under
  `client/`, which builds Zod 4 schemas from those plans and replays the same
  conformance corpus the Python suite runs.
- Response models: `QuestionnaireResponse`, `PageResponse` and `Answer`. Pages
  are recorded as filled or skipped -- by the respondent, or because their
  condition did not hold -- so where a response stands is derived from what is
  written down rather than tracked separately.
- `Page.is_skippable`, and a `submissions` service layer with `start_response`,
  `submit_page`, `skip_page` and `sync_condition_skips`.
- An opt-in JSON API under `vinta_django_questionnaires.urls` for opening a
  response, pushing one page's answers and skipping a page, plus
  `buildPageSchema` and `validatePage` on the client for checking that page
  before it is pushed.
- A React demo under `demo/` -- TanStack Start, Vite and the
  vinta-schedule-design-system -- that renders and validates a questionnaire
  entirely from the plan, including a client implementation of a custom
  validator and a panel showing what only the server can check. It ships a
  contrast audit script, and every text node in it passes WCAG 2.1 AA.
- The plan now carries what a client needs to render: each layer's resolved
  column count and each question's minimum columns, the questionnaire's window
  size ranges, titles, descriptions, and the widget and props the server
  resolved.
- `GET value-sets/{key}/options/`, which resolves a static or model-backed
  value set's options and hands back the endpoint descriptor for one the client
  is meant to call itself.
- `ResponseCreateView.get_external_id()`, so a project can key a response on
  something other than the request body -- the example uses the browser
  session.
- A runnable example project under `example/`, with a `seed_example` command
  that builds a four-page questionnaire exercising conditions, a skippable
  page, a nested sub-questionnaire, a model-backed value set and two
  project-specific validators, and a `demo_response` command that narrates a
  whole response through the flow. CI runs both.
- Validators now receive the response and page being submitted under
  `context.extra`, which is what a server-only validator needs to see anything
  wider than the answer in front of it.
- `new_version_from()`, which deep-copies a version into a new draft: the
  ordinary way to change a questionnaire that is already in use.
- An acknowledgement gate on editing a live definition in place. Once a version
  has responses, saving or deleting one of its pages, sections, questions,
  choices or validators raises `UnacknowledgedEdit` unless it happens inside
  `acknowledged_edit()`, which records who did it, why, what changed field by
  field, and how many responses were already in. `AcknowledgedEditForm` and
  `AcknowledgedEditAdminMixin` put that in front of someone as a checkbox.
- Content fingerprints on questions and versions, and `compare_versions()`, for
  telling which questions ask the same thing across versions and whose answers
  can therefore be pooled.
- The editable definition document: `definition_document()` reads a version as
  everything an author configured, and `apply_definition()` writes one back.
  Keys are identity, so a rename is a delete and a create; a document that does
  not hold up is refused whole, with one entry per node that would not go and
  the paths the editor addresses its own state by.
- `editor_catalog()`, which tells an editor what there is to pick: the question
  types, the widgets and their props schemas, the value sets, and every
  registered validator with its params schema and error keys -- including the
  ones other apps registered.
- An opt-in authoring API under `vinta_django_questionnaires.editor_urls` for
  reading a version, applying a document, forking a draft and fetching the
  catalog. Staff only by default, and `PUT` carries the acknowledgement that
  editing a live version needs.
- `QuestionnaireEditor`, a React editor in the client package under the
  `/editor` entry point, with `useQuestionnaireEditor` for a project that wants
  its own interface and a reducer under that with no React in it at all. It
  renders validator params from their own JSON Schema rather than a form per
  validator, names the answers a renamed key would orphan, puts the server's
  refusals under the field that caused them, and is styled entirely through
  `vqe-` class names and custom properties. The demo grows an `/editor` route
  that drops it in whole.
- An admin the package registers itself, arranged around what someone does
  rather than around the model graph. A questionnaire lists its versions with a
  way into each; a version's change form holds only the version's own settings;
  and a **structure editor** puts every page, section, question, choice and
  validator of a version on one form that saves together -- so a change across
  three levels is one save and one acknowledgement rather than five page loads
  and four of each. Rows show the key, title and type with the rest behind a
  disclosure, lists reorder by dragging or with the arrow keys, and the
  validator dropdown is the registry.
- The admin's response table: a column per question, a picker grouped by page,
  a CSV export of exactly the columns on screen, and a changelist action that
  exports a selection. It uses the same `reporting` module as the API and the
  React demo, so the three cannot drift.
- Every response now shows what it wrote and what it set off -- its
  `MappingRun`s with a link to the record each one created, and its
  `WebhookDelivery`s with the status and the error -- as read-only inlines.
- `admin.py` became the `admin` package; `AcknowledgedEditAdminMixin`,
  `AcknowledgedEditInlineMixin` and `signed_form` import from the same place as
  before.
- Registering the admin is opt-out. `QUESTIONNAIRES_REGISTER_ADMIN = False` and
  `register()`, which skips what is already registered -- so a project with an
  admin of its own for any of these models no longer fails to start with
  `AlreadyRegistered`. `register(model_admin_base=..., inline_base=...)` puts a
  themed admin's base classes underneath, inlines included, which is all a
  project on django-unfold needs.
- The admin stylesheet's colours became `--vqa-` tokens mapped onto the Django
  admin's, each falling back to a value mixed out of `currentColor`. A theme
  that replaces the admin's stylesheet defines none of Django's properties, and
  an unguarded `var()` there is invalid at computed-value time -- which
  collapsed every border in the structure editor to nothing. The editor now
  styles its own controls too, rather than leaning on the admin to do it.
- The changelists whose columns render those links now ship the stylesheet, so
  the shortcuts are buttons rather than bare text.
- `ResponseMapping` and `MappingField`: answers into a project's own models,
  named through the content type framework so this package never imports them.
  One JMESPath expression per target field, an operation of insert, update or
  upsert, defaults for what is created, and lookup fields for what is found.
  Every run is written down as a `MappingRun`, the target reachable from it.
- `ResponseWebhook`: a URL template with JMESPath-filled placeholders, and
  headers and a body that are JSON trees with `{"$jmespath": "..."}` resolved
  anywhere in them. Delivery goes through the standard library, is swappable
  through `QUESTIONNAIRES_WEBHOOK_SENDER`, and is recorded either way as a
  `WebhookDelivery`.
- Both run after the submission commits and neither can break one: a failure is
  a record, not something the respondent sees. `QUESTIONNAIRES_RUN_INTEGRATIONS`
  turns the inline run off for a project that would rather use a task queue.
- `reporting`: responses as a table. One column per question the version asks
  plus the metadata anyone reading a table wants, the same column list driving
  the JSON listing and a streamed CSV export, and one query for a whole page's
  answers rather than one per row.
- `GET responses/` and `GET responses/export/` on the authoring API, filtered by
  questionnaire, version, status and search, with the columns chosen per call.
- `POST questionnaires/new/`, `DELETE questionnaires/{key}/` and
  `DELETE questionnaires/{key}/versions/{n}/`, so the whole lifecycle of a
  questionnaire is reachable over HTTP. Deleting is refused once a version has
  been answered.
- Drag to reorder in the editor -- pages, sections, questions, choices and the
  validator chain -- on dnd-kit, an optional peer dependency. A `DndContext` per
  list, so a drag cannot take a question out of its section, and dnd-kit's
  keyboard sensor makes every list reorderable without a mouse.
- `AuthoringApi` in the client: `EditorApi` plus listing, creating and deleting
  questionnaires and reading responses, with `cellText` and `groupColumns` for
  rendering a table of them.
- The demo grows a back office: a sign-in page taking the Django admin's
  credentials, the editor and a TanStack Table of responses behind a staff gate,
  a column picker grouped by page, and a CSV button. The seed adds a mapping
  that turns a finished onboarding response into a `Lead`.
- `openapi.yml`, describing both URL modules -- every path, method, parameter
  and payload. The suite checks it against the URLconf, so an endpoint added
  without an entry fails CI.
- `QuestionnaireVersion.edit_policy`, `responses_due_at` and `edits_due_at`.
  Answering a page with nothing recorded and editing one that already has
  answers are separate acts with their own deadline, enforced by the
  submission layer and reported to the client as a `policy` block on every
  response payload.


<!--
  On release, move the entries above under a dated heading and repoint the links:

      ## [0.1.0] - YYYY-MM-DD

      [Unreleased]: https://github.com/vintasoftware/vinta-django-questionnaires/compare/v0.1.0...HEAD
      [0.1.0]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.1.0
-->

[Unreleased]: https://github.com/vintasoftware/vinta-django-questionnaires/commits/main
