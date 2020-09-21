# Generated by Django 2.2.16 on 2020-09-21 21:35

from django.db import migrations, models
import polaris.models


class Migration(migrations.Migration):

    dependencies = [
        ("polaris", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="envelope",
            field=models.TextField(null=True, validators=[polaris.models.deserialize]),
        ),
        migrations.AddField(
            model_name="transaction",
            name="pending_signatures",
            field=models.BooleanField(default=False),
        ),
    ]
