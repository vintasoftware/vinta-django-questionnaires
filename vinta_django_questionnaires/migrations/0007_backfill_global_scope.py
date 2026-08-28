"""Put everything that exists into the global scope.

An installation upgrading into scopes has one boundary today, whether or not it
calls it anything -- so every row lands in the scope that stands for "the whole
installation", and nothing changes about what anyone can see.

This is also why 0008 can add per-scope uniqueness without risking a conflict:
the keys it constrains were globally unique before this ran, and they all end up
in the same scope, so ``(scope, key)`` is unique by construction.
"""

from django.conf import settings
from django.db import migrations

GLOBAL = "global"


def put_everything_in_the_global_scope(apps, schema_editor):
    scope_model = apps.get_model(settings.QUESTIONNAIRES_SCOPE_MODEL)
    db = schema_editor.connection.alias

    scope = scope_model.objects.using(db).filter(scope_type=GLOBAL).first()
    if scope is None:
        # ``scope_key`` is "" for the global scope, which the historical model
        # cannot work out for itself -- ``build_scope_key`` is not carried into
        # a migration state.
        scope = scope_model.objects.using(db).create(scope_type=GLOBAL, scope_key="")

    for label in ("Questionnaire", "ValueSet", "QuestionnaireResponse"):
        model = apps.get_model("vinta_django_questionnaires", label)
        model.objects.using(db).filter(scope__isnull=True).update(scope=scope)

    response = apps.get_model("vinta_django_questionnaires", "QuestionnaireResponse")
    response.objects.using(db).update(scope_key=scope.scope_key)


def take_everything_back_out(apps, schema_editor):
    db = schema_editor.connection.alias
    for label in ("Questionnaire", "ValueSet", "QuestionnaireResponse"):
        model = apps.get_model("vinta_django_questionnaires", label)
        model.objects.using(db).update(scope=None)
    # The scope row itself is left alone: re-running this migration forward
    # finds it again, and deleting it would be the one destructive step in an
    # otherwise reversible pair.


class Migration(migrations.Migration):
    dependencies = [
        ("vinta_django_questionnaires", "0006_questionnairescope"),
        migrations.swappable_dependency(settings.QUESTIONNAIRES_SCOPE_MODEL),
    ]

    operations = [
        migrations.RunPython(
            put_everything_in_the_global_scope,
            take_everything_back_out,
        ),
    ]
