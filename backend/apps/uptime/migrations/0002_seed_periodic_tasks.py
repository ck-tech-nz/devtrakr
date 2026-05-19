from django.db import migrations


def seed_periodic_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=60, period="seconds",
    )
    PeriodicTask.objects.get_or_create(
        name="系统监控节拍（每分钟）",
        defaults={
            "task": "apps.uptime.tasks.tick_uptime_monitors",
            "interval": every_minute,
            "enabled": True,
        },
    )

    daily_3am, _ = CrontabSchedule.objects.get_or_create(
        minute="0", hour="3", day_of_month="*",
        month_of_year="*", day_of_week="*",
    )
    PeriodicTask.objects.get_or_create(
        name="清理过期监控记录（每日 3 点）",
        defaults={
            "task": "apps.uptime.tasks.prune_old_checks",
            "crontab": daily_3am,
            "enabled": True,
        },
    )


def remove_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(
        task__in=[
            "apps.uptime.tasks.tick_uptime_monitors",
            "apps.uptime.tasks.prune_old_checks",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("uptime", "0001_initial"),
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.RunPython(seed_periodic_tasks, remove_periodic_tasks),
    ]
