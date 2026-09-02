# vinta-django-questionnaires-client

Two things for [vinta-django-questionnaires](../README.md): [Zod 4](https://zod.dev)
schemas built from the validation plans it emits, so a questionnaire is
validated the same way in the browser and on the server -- and a React editor
for authoring the questionnaires themselves.

```bash
npm install vinta-django-questionnaires-client zod
```

React and [dnd-kit](https://dndkit.com) are peer dependencies, and optional
ones: the schema half of the package does not import either.

```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/modifiers @dnd-kit/utilities
```

## Using a plan

The server sends the plan; this package turns it into a schema.

```ts
import { buildQuestionnaireSchema } from "vinta-django-questionnaires-client"

const plan = await fetch("/questionnaires/intake/plan").then((response) => response.json())
const schema = buildQuestionnaireSchema(plan)

const result = schema.safeParse(answers)
```

Issues land at the answering question's key, and carry the error key the
server declared:

```ts
import { errorKeysOf } from "vinta-django-questionnaires-client"

if (!result.success) {
  errorKeysOf(result.error) // ["too_short"]
  result.error.issues[0].path // ["email"]
}
```

For a single field -- what a form library usually wants -- use
`buildQuestionSchema(questionPlan, { answers })`. Passing `answers` is what
lets cross-field predicates see the sibling questions.

## One page at a time

Responses are pushed a page at a time, and each page is validated on its own.
`buildPageSchema` gives that page's form its schema:

```ts
import { buildPageSchema } from "vinta-django-questionnaires-client"

const page = plan.pages.find((entry) => entry.key === response.progress.current)!
const schema = buildPageSchema(page, { answers: response.answers })
```

Pass the answers already recorded as `options.answers`. What a page is asking
is decided against the answers as they will be once the payload lands -- the
same merge the server does -- so a question whose condition depends on an
answer in the same payload behaves identically on both sides.

Then push the page and let the server have the last word; a page it rejects
comes back as a 422 shaped like `ValidationErrorPayload`, keyed by question.

`page.isSkippable` says whether to offer a Skip button, which posts to that
page's `skip/` endpoint. `response.progress` says where the respondent is:
`current` is the page to show, and a page skipped with reason `manual_action`
is still listed in `pending`, because skipping means later, not never.

`applicableQuestions(plan, answers)` returns the questions whose conditions
hold, which is also what decides what gets validated. Rendering and validation
therefore agree by construction.

## Custom validators

A validator the server marks as custom needs an implementation here, under the
same key it is registered with in Python:

```ts
import { registerClientValidator } from "vinta-django-questionnaires-client"

registerClientValidator("is_company_domain", {
  validate(value, params, ctx) {
    if (typeof value === "string" && !value.endsWith(`@${params.domain}`)) {
      ctx.fail("foreign_domain")
    }
  },
})
```

`ctx.chain` exposes what the earlier checks recorded, the same way the Python
context does.

## When something is missing

A plan can name a validator this build does not have -- the server shipped
before the frontend did. That check is skipped, never blocking the respondent,
and the server still enforces it on submit. Nothing is silent, though:

```ts
import { onDiagnostic } from "vinta-django-questionnaires-client"

onDiagnostic((diagnostic) => {
  Sentry.captureMessage(diagnostic.message, {
    level: "warning",
    tags: { code: diagnostic.code, validator: diagnostic.validator },
  })
})
```

Diagnostics are deduplicated per distinct problem, so a re-render does not
flood the reporter. The codes are `missing-validator`, `unknown-check`,
`server-only`, `condition-error` and `plan-version`. With no subscriber, a
console warning is used instead -- except for `server-only`, which is a
configuration rather than a problem.

## The editor

A React editor for the questionnaire definitions themselves, against the
authoring API described in the [main README](../README.md#the-authoring-api-and-the-react-editor).

```tsx
import { createEditorClient } from "vinta-django-questionnaires-client"
import { QuestionnaireEditor } from "vinta-django-questionnaires-client/editor"
import "vinta-django-questionnaires-client/editor.css"

const api = createEditorClient({
  baseUrl: "/api/authoring/",
  headers: () => ({ "X-CSRFToken": csrfToken() }),
})

<QuestionnaireEditor api={api} questionnaire="intake" version={2} />
```

Nothing about a question type, a validator or a widget is written down in the
editor. It reads the catalog: a validator another Django app registers appears
in the dropdown with its own params rendered from its own JSON Schema, and a
question type that takes no choices does not offer them. The one thing to keep
in step is this package's `SUPPORTED_DOCUMENT_VERSION` against the server's
`DOCUMENT_VERSION`.

What it does that a plain form would not:

- **It says what an edit costs.** Rename a question's key and it names the
  answers that will be orphaned by it, before you save. Edit a version that has
  responses and it will not save until the acknowledgement box is ticked --
  which is the same gate the Python side enforces, so the box is not decoration.
- **It puts the server's own errors where they happened.** A refused save comes
  back addressed by node path, and the editor addresses its state the same way,
  so a message about `pages.0.sections.1.questions.2` lands under that
  question's field rather than at the top of the page.
- **It checks what it can without asking.** Empty and clashing keys, choices
  storing the same value, a validator that does not apply to the question's
  type. The server still has the last word and says so in the same shape.
- **Everything ordered is dragged.** Pages, sections, questions, choices and
  the validator chain. There is a `DndContext` per list rather than one for the
  whole editor, which is what makes a drag unable to take a question out of its
  section: that is not a move the questionnaire's shape has, and the cheapest
  way to make it impossible is not to model it. dnd-kit's keyboard sensor comes
  with it, so every list reorders from the keyboard too -- tab to a handle,
  space to lift, arrows to move, space to drop.

### The rest of the back office

`createEditorClient` returns an `AuthoringApi`, which is `EditorApi` plus what
the editor never touches:

```ts
await api.listQuestionnaires()
await api.createQuestionnaire({ key: "intake", name: "Intake" })
await api.deleteVersion("intake", 3)

const page = await api.listResponses({ questionnaire: "intake", page: 1, pageSize: 25 })
window.location.href = api.responseExportUrl({ questionnaire: "intake", columns: shown })
```

`listResponses` hands back the rows *and* every column there was to pick, so a
table can offer a column picker without knowing what the questionnaire asks.
`cellText` renders a value the way the CSV export does, and `groupColumns`
arranges the picker by page. The demo builds a TanStack Table on exactly that.

### Styling

Every element carries a `vqe-` class name and every colour is a custom property
on `.vqe`, so a project can retheme it without forking:

```css
.vqe {
  --vqe-accent: var(--brand-500);
  --vqe-radius: 2px;
}
```

It is light unless you pass `theme="dark"`. It deliberately does not read
`prefers-color-scheme`: the page it sits in decides its own theme, and an app
that pins itself light on a machine set to dark would otherwise get a dark
editor inside a light page. Both palettes pass WCAG 2.1 AA.

Or skip `editor.css` entirely and style those class names yourself.

### Speaking another language

The package carries no i18n dependency: which one to use belongs to the project
installing this, not to the library. Instead every word the editor says lives
in a catalogue keyed by name, and a host replaces as much of it as it likes:

```tsx
<QuestionnaireEditor
  api={api}
  questionnaire="intake"
  version={2}
  strings={{
    "editor.save": "Salvar",
    "field.title": "Título",
    "editor.issues.heading": ({ count }) =>
      count === 1
        ? "1 coisa a corrigir antes de salvar:"
        : `${count} coisas a corrigir antes de salvar:`,
  }}
/>
```

Whatever is left out stays English, so a catalogue can be filled in over time
and a key added by a later release never leaves a blank on the screen. Import
`defaultStrings` for the full list, or read `src/strings.ts`.

Most entries are a plain string, because most sentences stand on their own. The
twenty-two that do not are functions, taking what the editor only knows as it
renders. There is no template syntax between the two -- no placeholder to spell
right, nothing substituted at run time -- and nothing to remember about which
key is which, because the type says so:

```tsx
t("editor.save")                             // ok
t("editor.issues.heading")                   // error: expected 2 arguments, got 1
t("editor.issues.heading", { cont: 3 })      // error: did you mean 'count'?
t("editor.issues.heading", { count: "3" })   // error: string is not a number

strings={{ "editor.save": () => "Salvar" }}  // error: expected a string
```

### Using the i18n library you already have

This is what the functions are for. Their parameters are only known as the
editor renders, so a finished string could never reach your `t()` carrying
them. A function can, and hands the whole sentence -- interpolation, plurals,
gender -- to whatever the project already uses:

```tsx
import { useTranslation } from "react-i18next"

const { t } = useTranslation()

<QuestionnaireEditor
  strings={{
    "editor.save": t("questionnaire.save"),
    "editor.issues.heading": ({ count }) => t("questionnaire.issues", { count }),
  }}
  {...props}
/>
```

The plain ones need no wrapping: call your `t()` as the object is built, which
happens on every render, so a change of locale reaches them like any other
state. Plurals are that library's problem, then, and it has real rules for them
-- which a catalogue of our own could not have had. The English defaults say
"response(s)" and leave it there.

A catalogue that arrives as data is already most of the way to this shape --
its plain strings go straight in, and only the parameterised keys need a
function written for them.

### Reaching the whole editor

Every part of the editor is exported on its own, so the catalogue rides a React
context rather than being threaded down as props. Composing your own interface,
wrap it once:

```tsx
import { QuestionnaireStringsProvider } from "vinta-django-questionnaires-client/editor"

<QuestionnaireStringsProvider strings={ptBR}>
  <Outline {...props} />
  <QuestionForm {...props} />
</QuestionnaireStringsProvider>
```

Each component also takes its own `strings` prop, which wins over the context
for that subtree. `useQuestionnaireEditor` reads the same catalogue, so the
problems it finds before a save are worded by it too.

Two things are deliberately not in the catalogue:

- **What a respondent sees when an answer fails.** Those messages are templates
  the server sends down in the plan, translated by Django, and this package
  only fills in their placeholders. Translating them here would mean
  translating them twice, differently.
- **Diagnostics and thrown `Error`s.** They go to consoles and error trackers,
  where a stable English string is worth more than a translated one.

### Building your own

`QuestionnaireEditor` is one component over a hook, and the hook is one layer
over a reducer that has no React in it at all:

```ts
import { useQuestionnaireEditor } from "vinta-django-questionnaires-client/editor"

const { state, dispatch, catalog, issues, isDirty, save, fork } =
  useQuestionnaireEditor({ api, questionnaire: "intake", version: 2 })

dispatch({ type: "insert", path: { page: 0, section: 1 } })
dispatch({ type: "moveItem", path, list: "validators", index: 0, by: 1 })
```

`editorReducer`, `validateDefinition`, `outgoingDocument` and the rest are
exported from the package root and are plain functions -- which is also how
they are tested.

`EditorApi` is the whole contract the editor depends on. A project with its own
HTTP client can implement those four methods and skip `createEditorClient`.

## How the two sides stay in agreement

Checks run inside a single `superRefine` rather than as a chain of native Zod
checks. That is deliberate: the server skips checks on empty answers, runs
them in a fixed order, and lets later checks read what earlier ones recorded.
Native Zod checks cannot express any of that, and a schema that quietly
disagreed with the server would be worse than no schema at all. The base type
is still Zod's, so a wrong shape is still a plain Zod type error.

Whether an answer may be missing is decided by the plan -- by a `required`
check being present -- never by the base type, which is why every base type is
nullish.

`shared/conformance-cases.json` is written by the Python suite and replayed by
this one. Both must produce the same error keys, in the same order.

## Scripts

| Command | What it does |
| --- | --- |
| `npm test` | Replay the conformance corpus and the client's own tests |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run build` | Emit `dist/` |
