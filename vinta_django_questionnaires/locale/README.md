# Translations

Django looks here for this app's catalogues, one directory per language:

    locale/<language>/LC_MESSAGES/django.po

There are none yet -- the app speaks English until someone adds one. Every
string it says is already wrapped in `gettext_lazy`, so adding a language is
extraction and translation, not a code change.

## Adding one

From the repository root, with `gettext` installed:

```bash
DJANGO_SETTINGS_MODULE=example.settings \
  uv run django-admin makemessages -l pt_BR --no-obsolete
```

Run it from inside `vinta_django_questionnaires/`, so the catalogue lands in
this directory rather than in the project that happens to be running it. Then
translate `locale/pt_BR/LC_MESSAGES/django.po` and compile it:

```bash
DJANGO_SETTINGS_MODULE=example.settings uv run django-admin compilemessages
```

## What is and is not in here

In: the admin, the editor's API, the model field names and help text, and every
validator's error messages -- including the message templates the client
formats and shows a respondent, which is why the browser needs no catalogue of
validation messages of its own.

Out: the editor's own interface, which is React and ships in the npm package.
It carries its own key/value catalogue, overridable through a `strings` prop.
See `client/src/strings.ts`.

## Committing the compiled files

`.mo` files are built from `.po` and are what Django actually reads. Commit
them alongside the `.po`: the package is published as a wheel, and a wheel is
not built in an environment that runs `compilemessages`.
