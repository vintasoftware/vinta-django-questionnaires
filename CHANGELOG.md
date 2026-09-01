# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [Unreleased]


## [0.2.2] - 2026-08-31

The editor's outline rail now reaches the bottom of the page. Splitting the
pinned element out from the one that paints the column is what makes both hold
at once, and it adds one `div` inside `nav.vqe-outline` -- the only thing here
a project styling the editor itself might notice.

### Fixed

- **The editor's outline rail stopped partway down the page.** The rail was the
  element being pinned, so it could only be as tall as the tree inside it --
  against a long inspector its surface and its right-hand border ended early
  and the rest of the column fell back to the page's own background, which read
  as a panel someone had forgotten to finish. On a version form it covered
  203px of an 1109px column.

  The rail and the thing that sticks are now two elements: `.vqe-outline`
  fills the grid row and paints it, and a new `.vqe-outline__pane` inside it is
  what stays level while the page scrolls. Both properties hold at once, which
  neither could alone -- something pinned needs room to move inside its
  container, and a full-height element leaves none.

  This adds one `div` inside `nav.vqe-outline`. A project styling the editor
  through its own stylesheet keeps working; one that had targeted
  `.vqe-outline > *` directly would need `.vqe-outline__pane > *`.


## [0.2.1] - 2026-08-31

Two fixes to the editor's stylesheet, both the same mistake seen twice: a rule
written for a field inside a row was reaching fields that stand on their own.
The forms are shorter and their inputs line up. Only `editor.css` changed; the
Python package moves with the npm one, as the two always do.

### Fixed

- **The editor's stacked fields were 192px tall whatever they contained.**
  `.vqe-field` carried `flex: 1 1 12rem`, which is right for a field inside a
  `.vqe-row` -- there 12rem is the width to wrap at -- but the forms also put
  fields directly inside `.vqe-form`, which is a column, and a flex basis along
  a column axis is a *height*. Every stacked field got a 12rem base height: the
  page form's condition field rendered 85px of content in a 192px box, more
  dead space than content, and the form ran to 769px instead of 543px. The
  basis now applies only inside a row.
- **A row's inputs did not line up.** `.vqe-row` aligned its fields at
  `flex-end`, so a field carrying a hint and one without it were matched at
  their bottoms, putting the unhinted field's input 27px below its neighbour's.
  Rows align at the start now: the inputs line up and the hints hang below
  them.


## [0.2.0] - 2026-08-27

Multi-tenancy. A questionnaire and a response each belong to a **scope** -- a
tenant, a workspace, or the installation at large -- through a swappable model.
Nothing is required: without configuration everything lands in one global scope
and behaves as it did before.

Three breaking changes, all listed below. The migration into this release cannot
fail on existing data: every row moves into one global scope, where the
uniqueness that held before still holds.

### Added

- **Multi-tenant scopes.** A questionnaire and a response each belong to a
  scope -- a tenant, a workspace, or the installation at large -- through a
  swappable model, the `AUTH_USER_MODEL` way. Point
  `QUESTIONNAIRES_SCOPE_MODEL` at your own subclass of
  `AbstractQuestionnaireScope`; leave it alone and everything lands in one
  global scope, exactly as before.
- A scope is set when a row is created and **never changed**, which is enforced
  rather than documented. That is what makes the `scope_key` copied onto each
  response safe: it cannot drift from the foreign key beside it.
- `ScopeFilter`, and a required `scopes` argument on `response_queryset()`.
- Scope-aware URLs. Mount either URL module under a prefix that captures a
  `scope_key` and Django hands it to every view underneath; the package picks
  no URL shape of its own, and an installation that mounts them unprefixed
  behaves as it always did.
- A scope filter in the admin's response table, and `scope` on the ordinary
  changelists. Staff still see every scope -- the control narrows what is on
  screen rather than deciding what may be seen.
- An optional scope on `ResponseMapping` and `ResponseWebhook`, so a shared
  questionnaire can reach a different endpoint per tenant, and `scope` in the
  expression document so a URL template can say `{scope}`.
- A second test run, `pytest tests/scoped --ds=tests.settings_scoped`, against a
  scope model the package does not own. `Meta.swappable` resolves once per
  process, so this cannot be an `override_settings`.

### Changed

- **Breaking.** `response_queryset()` requires a `scopes` keyword argument. A
  boundary that defaults to open is the failure this exists to prevent, so a
  single-tenant installation writes `ScopeFilter.everything()` at the call site.
- **Breaking.** `Questionnaire.key` and `ValueSet.key` are unique per scope
  rather than across the installation, so two tenants may each have an
  `intake`. Existing rows migrate into one global scope, where the old
  uniqueness still holds, so the migration cannot fail on duplicates.
- **Breaking.** The admin response table's `questionnaire` filter takes a
  primary key rather than a key. Staff span every scope and keys are no longer
  unique across them, so two tenants' `intake` would otherwise select as one
  and merge their answers under a single set of columns.
- The authoring API's questionnaire listing now sends `scope` and `isGlobal`
  alongside each entry, so a client never has to work out which of two
  same-keyed questionnaires it is looking at.

### Fixed

- The release workflow uploaded the signed artifacts to the release twice: the
  signing action attaches them itself now, and the hand-written `gh release
  upload` after it failed on the second copy. Both packages of 0.1.1 published
  before it ran, and the release carries its signatures; only the workflow's
  own result was red.


## [0.1.1] - 2026-08-27

The two packages share a version from here on, and go out on one `vX.Y.Z` tag.
CI refuses a commit where `pyproject.toml` and `client/package.json` disagree.

Nothing in the Django app changed: it is republished only to keep the pair in
step. Everything below is the npm package or the release plumbing.

### Fixed

- The published client's inline documentation pointed at
  `@vintasoftware/django-questionnaires`, a package that does not exist -- 0.1.0
  went to npm from a build made before the rename reached the doc comments.
- The client package declared no `repository`, `homepage` or `bugs`, and left
  the licence out of the tarball. `repository` is not cosmetic: npm's provenance
  attestation names the source of a build, so without it the release workflow
  cannot publish at all.
- The release signing action was pinned to a version from before Sigstore
  rotated its TUF root, and failed with `root was signed by 0/3 keys`. It runs
  after the upload, so 0.1.0 reached PyPI with its PEP 740 attestations intact
  but without Sigstore bundles on its GitHub release.

### Changed

- Both packages release from the same tag. `publish-client.yml` no longer waits
  on a `client-v*` tag of its own, and `publish.yml` no longer has to ignore one.


## [0.1.0] - 2026-08-27

### Added

- Initial project scaffolding.
- `publish.yml` and `publish-client.yml`, which release the Django app to PyPI
  and the TypeScript client to npm through trusted publishing -- no token is
  stored on either side.
- Questionnaire definition models: versioned questionnaires, pages, sections,
  questions, inline choices, value sets, widgets and the responsive column
  grid, with conditions evaluated through JMESPath.
- A dynamic validation layer: a validator registry other apps extend with
  `@register_validator`, and 24 built-in validators covering presence, text,
  numbers, dates and ranges, collections, files and cross-field predicates.
- A validation plan emitted per question or questionnaire version, and the
  `dump_validation_manifest` and `dump_conformance_cases` commands that write
  the artifacts under `shared/`.
- `vinta-django-questionnaires-client`, the TypeScript client under
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

[0.2.2]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.2.2
[0.2.1]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.2.1
[0.2.0]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.2.0
[0.1.1]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.1.1
[0.1.0]: https://github.com/vintasoftware/vinta-django-questionnaires/releases/tag/v0.1.0
