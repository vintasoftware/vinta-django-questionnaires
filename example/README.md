# The example project

A runnable Django project with a seeded questionnaire, so the package can be
poked at without wiring anything up.

```bash
uv sync --all-groups
uv run python -m example.manage migrate
uv run python -m example.manage seed_example
uv run python -m example.manage runserver
```

Then sign in at http://localhost:8000/admin/ as `demo` / `demo`.

## What gets seeded

Two questionnaires. **client-onboarding** is the interesting one -- four pages,
fourteen questions, published, with a response deadline a month out:

| Page | What it shows |
| --- | --- |
| `about` | Required text, an email with a project-specific validator on top, a single choice, and questions that appear only when you say you have a company |
| `project` | A number with bounds, a date range, a multiple choice with an "other" option and item limits, a select from a model-backed value set, and a repeatable sub-questionnaire |
| `billing` | A page with its own condition -- only companies are asked |
| `extras` | Skippable, with a file question size- and type-limited |

**team-member** is the small questionnaire that `project` nests as a list.

Around them: nine widgets with real props schemas, a static value set, a value
set backed by `auth.Group` and narrowed with the filter DSL
(`name startswith "tech-"`), three breakpoints, and column counts set at the
version, page and section levels.

`example/questionnaire_validators.py` registers two validators the package does
not ship: `business_email`, which the browser is expected to implement too, and
`unique_company_name`, which only the server can answer.

Re-run `seed_example` any time; it updates in place. `--reset` clears the data
first, responses included.

## Watching it work, without a browser

```bash
uv run python -m example.manage demo_response
```

That drives a response through the whole flow and narrates it: a page rejected
by its validators, a page ruled out by its condition, a page put off for later,
a completed response refusing an edit, a new version forked from the old one,
and an edit made in place with an acknowledgement on the record. It resets
itself first, so it can be run repeatedly.

## Over HTTP

```bash
uv run python -m example.manage runserver
```

The API is mounted at `/api/questionnaires/`. It needs a signed-in respondent,
so the quickest way to try it is Django's own test client:

```python
from django.test import Client
from django.contrib.auth import get_user_model

client = Client()
client.force_login(get_user_model().objects.get(username="demo"))
created = client.post(
    "/api/questionnaires/responses/",
    data='{"questionnaire": "client-onboarding"}',
    content_type="application/json",
).json()

created["progress"]  # where to start, and what was already ruled out
created["policy"]  # what this version still accepts
created["plan"]  # what the TypeScript client builds its Zod schemas from
```

Push a page to `responses/{id}/pages/about/` and skip one at
`responses/{id}/pages/extras/skip/`.

## Things worth trying in the admin

- Edit a question on `client-onboarding` **after** running `demo_response`, which
  leaves a response behind. The change form asks you to tick a box first, and
  what you tick is kept under **Acknowledged edits** with the diff.
- Look at a **Questionnaire response**: its page responses say which pages were
  filled, which were skipped, and why.
- Add a `tech-` group under **Groups** and watch it appear in the `stack`
  question's value set.
