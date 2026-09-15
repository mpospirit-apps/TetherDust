"""Drop ``Role.can_view_tethers``: tether access is now just the tethers shared with a role.

The flag was a second gate on top of ``Tether.allowed_roles``. Without it, a role
that had the flag off but still had tethers shared with it would suddenly see
them, so those shares are removed first — nobody gains access they didn't have.
"""

from __future__ import annotations

from django.db import migrations


def unshare_tethers_from_flagged_off_roles(apps, schema_editor):
    Tether = apps.get_model("engine", "Tether")
    Tether.allowed_roles.through.objects.filter(role__can_view_tethers=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("engine", "0012_role_row_limit_floor_and_inactive_admin"),
    ]

    operations = [
        migrations.RunPython(unshare_tethers_from_flagged_off_roles, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="role",
            name="can_view_tethers",
        ),
    ]
