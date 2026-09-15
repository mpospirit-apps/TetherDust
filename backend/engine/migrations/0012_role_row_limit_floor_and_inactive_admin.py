"""Floor a role's row limit at 1, and stop inactive admin roles granting staff.

A limit below 1 went straight into the SQL — ``LIMIT 0`` returned nothing and a
negative one failed every query — so those roles go back to the default of 100.
An inactive role now grants nothing, so non-superusers whose only claim to staff
was an inactive admin role are demoted, as saving the role would now do.
"""

from __future__ import annotations

import django.core.validators
from django.db import migrations, models


def repair_roles(apps, schema_editor):
    Role = apps.get_model("engine", "Role")
    User = apps.get_model("auth", "User")
    Role.objects.filter(max_row_limit__lt=1).update(max_row_limit=100)
    User.objects.filter(
        is_superuser=False,
        profile__role__is_admin_role=True,
        profile__role__is_active=False,
    ).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("engine", "0011_drop_unwired_system_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="max_row_limit",
            field=models.IntegerField(
                default=100,
                help_text="Maximum rows per query",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="max row limit",
            ),
        ),
        migrations.RunPython(repair_roles, migrations.RunPython.noop),
    ]
