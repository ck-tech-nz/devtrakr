import django.db.models.deletion
from django.db import migrations, models


def migrate_role_string_to_group(apps, schema_editor):
    """Map existing role string values to auth.Group rows by name."""
    ProjectMember = apps.get_model("projects", "ProjectMember")
    Group = apps.get_model("auth", "Group")
    cache: dict[str, int | None] = {}
    for member in ProjectMember.objects.all():
        raw = (member.role or "").strip()
        if not raw:
            continue
        if raw not in cache:
            group = Group.objects.filter(name=raw).first()
            cache[raw] = group.pk if group else None
        member.role_group_id = cache[raw]
        member.save(update_fields=["role_group"])


def reverse_role_group_to_string(apps, schema_editor):
    ProjectMember = apps.get_model("projects", "ProjectMember")
    for member in ProjectMember.objects.select_related("role_group").all():
        member.role = member.role_group.name if member.role_group_id else ""
        member.save(update_fields=["role"])


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectmember",
            name="personal_description",
            field=models.TextField(blank=True, default="", verbose_name="个人描述"),
        ),
        migrations.AddField(
            model_name="projectmember",
            name="role_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_memberships",
                to="auth.group",
                verbose_name="角色",
            ),
        ),
        migrations.RunPython(
            migrate_role_string_to_group,
            reverse_code=reverse_role_group_to_string,
        ),
        migrations.RemoveField(
            model_name="projectmember",
            name="role",
        ),
        migrations.RenameField(
            model_name="projectmember",
            old_name="role_group",
            new_name="role",
        ),
    ]
