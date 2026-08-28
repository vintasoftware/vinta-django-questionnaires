"""Tighten the scope columns, and move key uniqueness onto the scope.

``key`` stops being unique across the installation and becomes unique within a
scope, which is what lets two tenants each have an ``intake``.  0007 guarantees
this cannot fail on existing data.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("vinta_django_questionnaires", "0007_backfill_global_scope"),
        migrations.swappable_dependency(settings.QUESTIONNAIRES_SCOPE_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="questionnaire",
            name="scope",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        migrations.AlterField(
            model_name="valueset",
            name="scope",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        migrations.AlterField(
            model_name="questionnaireresponse",
            name="scope",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(app_label)s_%(class)s_set",
                to=settings.QUESTIONNAIRES_SCOPE_MODEL,
                verbose_name="scope",
            ),
        ),
        # The keys lose their installation-wide uniqueness ...
        migrations.AlterField(
            model_name="questionnaire",
            name="key",
            field=models.SlugField(
                help_text="Stable identifier, shared by every version. Unique within a scope.",
                max_length=100,
                verbose_name="key",
            ),
        ),
        migrations.AlterField(
            model_name="valueset",
            name="key",
            field=models.SlugField(max_length=100, verbose_name="key"),
        ),
        # ... and get it back, per scope.
        migrations.AddConstraint(
            model_name="questionnaire",
            constraint=models.UniqueConstraint(
                fields=("scope", "key"), name="unique_questionnaire_key_per_scope"
            ),
        ),
        migrations.AddConstraint(
            model_name="valueset",
            constraint=models.UniqueConstraint(
                fields=("scope", "key"), name="unique_value_set_key_per_scope"
            ),
        ),
        migrations.AddIndex(
            model_name="questionnaireresponse",
            index=models.Index(
                models.F("scope_key"),
                models.OrderBy(models.F("created_at"), descending=True),
                name="response_scope_recent_idx",
            ),
        ),
    ]
