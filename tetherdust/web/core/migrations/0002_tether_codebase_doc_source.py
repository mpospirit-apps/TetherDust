"""Allow a codebase documentation source as a tether's code side.

Makes ``Tether.codebase`` optional and adds ``Tether.codebase_doc_source`` so
the code side can be either a live codebase repository or a codebase doc source
(exactly one, enforced in ``Tether.clean()`` / the admin form).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tether",
            name="codebase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text=(
                    "Code side: a live codebase repository (mutually exclusive with codebase doc)."
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tethers",
                to="core.codebase",
            ),
        ),
        migrations.AddField(
            model_name="tether",
            name="codebase_doc_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text=(
                    "Code side: a codebase documentation source (mutually exclusive with codebase)."
                ),
                limit_choices_to={"doc_type": "codebase"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tethers_as_codebase",
                to="core.documentationsource",
            ),
        ),
    ]
