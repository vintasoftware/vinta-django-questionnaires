"""The scope model, and a nullable column on everything that belongs to one.

Split into three migrations rather than one because the columns end up NOT
NULL: this adds them nullable, 0007 fills them in, and 0008 tightens them.  An
installation upgrading into this has rows already, and there is no default a
foreign key could carry that would suit them.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vinta_django_questionnaires", "0005_responsemapping_responsewebhook_mappingrun_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestionnaireScope",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
                (
                    "scope_type",
                    models.CharField(
                        choices=[("global", "Global"), ("scoped", "Scoped")],
                        default="global",
                        max_length=20,
                        verbose_name="scope type",
                    ),
                ),
                (
                    "scope_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text=(
                            "Stable string form of this scope. "
                            "Never changes once records reference it."
                        ),
                        max_length=255,
                        verbose_name="scope key",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="label"
                    ),
                ),
                (
                    "_scope",
                    models.CharField(
                        blank=True, default="", max_length=255, verbose_name="scope"
                    ),
                ),
            ],
            options={
                "verbose_name": "questionnaire scope",
                "verbose_name_plural": "questionnaire scopes",
                "ordering": ["scope_type", "scope_key"],
                "swappable": "QUESTIONNAIRES_SCOPE_MODEL",
            },
        ),
        migrations.AddConstraint(
            model_name="questionnairescope",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("_scope", ""),
                    ("scope_type", "global"),
                )
                | (~models.Q(("scope_type", "global")) & ~models.Q(("_scope", ""))),
                name="questionnaire_scope_type_and_value_agree",
            ),
        ),
        migrations.AddConstraint(
            model_name="questionnairescope",
            constraint=models.UniqueConstraint(
                fields=("scope_type", "scope_key"),
                name="questionnaire_scope_unique_key_per_type",
            ),
        ),
        migrations.AddField(
            model_name="questionnaire",
            name="scope",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        migrations.AddField(
            model_name="valueset",
            name="scope",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        migrations.AddField(
            model_name="questionnaireresponse",
            name="scope",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        migrations.AddField(
            model_name="questionnaireresponse",
            name="scope_key",
            field=models.CharField(
                blank=True, default="", max_length=255, verbose_name="scope key"
            ),
        ),
    ]
