# The React demo

A TanStack Start app that fills in the seeded questionnaire, so the whole loop
can be seen working: the server sends a plan, the browser renders and validates
from it, and the server has the last word.

```bash
# One terminal: the Django example project
uv run python -m example.manage migrate
uv run python -m example.manage seed_example
uv run python -m example.manage runserver

# Another: this app (it builds the client package first)
npm --prefix demo install
npm --prefix demo run dev
```

Then open http://localhost:5273.

Vite proxies `/demo-api` to Django on port 8000, so the browser stays on one
origin and the session and CSRF cookies behave the way they would in production
behind a single domain.

## What it demonstrates

- **The plan drives everything.** No question, validator, choice or layout is
  written in this app. `plan.pages` is what it renders, and a change in the
  Django admin shows up on reload.
- **The same rules on both sides.** `buildPageSchema(page, { answers })` gives
  the page's form its Zod schema, so `min_length` and `email` fail before any
  round trip, in the words the server chose. The page is validated again on
  submit, and a 422 is shown the same way as a local failure.
- **A custom validator, twice.** `business_email` is registered in Python and,
  under the same key, in `src/validators.ts`, so the browser refuses a personal
  address on its own.
- **A validator that cannot run in a browser.** `unique_company_name` is
  `ClientSpec.server_only()`. The client skips it, marks the question *checked
  on submit*, and reports it through `onDiagnostic` -- which the panel on the
  right shows, standing in for the Sentry call a real app would make.
- **Conditions, live.** Answer "yes" to the company question and two questions
  appear on the page, while *Billing* changes from *Not asked* to *Pending* in
  the progress panel: the same JMESPath the server evaluates on save.
- **The responsive grid.** `Grid` and `GridItem` take their columns from the
  plan, so the widths a questionnaire author set per breakpoint are what the
  browser lays out.
- **Widgets as components.** The seeded widget keys *are* design system
  component names, and the widget props are that component's props, validated
  against its JSON Schema on save. `widgetProps` is spread onto the component
  with nothing in between.

- **The editor, dropped in whole.** `/editor` renders the package's
  `QuestionnaireEditor` against the same server, styled by nothing in this app.
  Change a title there and reload the form to see it. The seeded version has a
  response against it, so the acknowledgement box has to be ticked first -- and
  what goes through is recorded as an `AcknowledgedEdit`, visible in the Django
  admin. Pages, sections, questions, choices and validators all reorder by
  dragging, or from the keyboard.
- **A back office behind a sign-in.** `/login` takes the Django admin's
  credentials -- `demo` / `demo` after seeding -- and hands out the ordinary
  Django session. Unlike the response API, the authoring endpoints here are
  *not* relaxed: they are the package's own, staff only.
- **Responses as a table.** `/responses` is a TanStack Table over
  `listResponses`, with a column picker grouped by page and a CSV export that
  takes the same columns, so the download matches the screen. Nothing in that
  screen knows what the questionnaire asks: the columns come down with the rows.
- **Answers becoming a `Lead`.** The seed adds a mapping from the onboarding
  questionnaire to `example.models.Lead` -- an ordinary model neither the
  package nor the questionnaire knows about -- as an upsert keyed on the email
  answer. Run `demo_response` and one appears in the admin, with a `MappingRun`
  next to it saying what happened. A webhook is seeded alongside it, switched
  off: turning it on reaches the internet, which a seeded example should not do
  on its own.

## Where things are

| File | What it does |
| --- | --- |
| `src/components/Questionnaire.tsx` | The flow: open a response, render the current page, submit or skip |
| `src/components/EditorScreen.tsx` | Pick a version, create and delete, then hand it to the package's editor |
| `src/components/ResponsesTable.tsx` | TanStack Table, the column picker, the CSV button |
| `src/components/SignIn.tsx` | The sign-in form, and the staff gate the back office sits behind |
| `src/auth.tsx` | Who is signed in, from Django's own session |
| `src/editorApi.ts` | `createEditorClient` pointed at the demo's authoring URLs |
| `src/components/QuestionField.tsx` | Widget key to design system component |
| `src/components/ProgressPanel.tsx` | Which pages are done, skipped and why, pending |
| `src/components/DiagnosticsPanel.tsx` | What the client could not check |
| `src/breakpoints.ts` | The questionnaire's window size ranges onto the design system's |
| `src/api.ts` | The `/demo-api` calls, with the CSRF header |

The design system is
[vinta-schedule-design-system](https://www.npmjs.com/package/vinta-schedule-design-system).

## Contrast

`scripts/contrast-audit.js` measures every piece of text on screen against
WCAG 2.1 AA. Paste it into the browser console and run it once per state that
matters -- a filled page, a page showing errors, the completed view -- since
each renders text the others do not.

Two things it found, both fixed:

- Secondary copy was set to the `muted` token, which is a *surface* colour --
  near-white text on white. It is `muted-foreground` that is meant for text.
  `ColorToken` ends in `(string & {})`, so TypeScript accepted the wrong one
  silently.
- With that corrected, the design system's `--muted-foreground` (slate-500)
  measures 4.36:1 on the combobox placeholder and 4.56:1 on card surfaces --
  either side of the 4.5:1 line. `src/styles.css` takes it to slate-600
  (~7:1) for the light theme only. That override belongs in the design system
  rather than here, and is worth raising against it.

As it stands every text node passes, with the lowest at 4.85:1 (the error
message inside a destructive alert) and secondary copy at 6.9-7.3:1.

## Things worth knowing

The app fetches on the client, in an effect. A real TanStack Start app would
use a route loader or a server function, which would also let it render the
first page on the server; this stays on the client so the whole exchange is
visible in the network tab.

The file question records the file and does not upload it. Uploads are the host
project's business -- the package stores whatever JSON the answer is.

`/demo-api` is the example project's own relaxed copy of the API, keyed on the
browser session and refusing to run with `DEBUG` off. The package's own
endpoints under `/api/questionnaires/` want a signed-in respondent, and the
authoring ones under `/api/authoring/` want a staff user; see `example/api.py`
for the difference. The edits the demo's editor makes are real: the
acknowledgement gate, the validation and the records all behave exactly as they
would behind a login.
