from django.db import migrations, models


def clear_names_from_telegram_profile(apps, schema_editor):
    # До этой миграции бот записывал в full_name имя из профиля Telegram,
    # а не имя ученика. Такие значения вводят менеджера в заблуждение.
    Lead = apps.get_model("leads", "Lead")
    Lead.objects.filter(source="telegram_bot").update(name="")


class Migration(migrations.Migration):

    dependencies = [
        ("leads", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(model_name="lead", old_name="full_name", new_name="name"),
        migrations.RunPython(clear_names_from_telegram_profile, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="lead",
            name="name",
            field=models.CharField(blank=True, max_length=100, verbose_name="имя ученика"),
        ),
        migrations.AlterField(
            model_name="lead",
            name="parent_name",
            field=models.CharField(blank=True, max_length=100, verbose_name="имя родителя"),
        ),
    ]
