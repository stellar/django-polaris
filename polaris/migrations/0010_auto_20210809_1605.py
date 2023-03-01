# Generated by Django 2.2.24 on 2021-08-09 16:05

from django.db import migrations, models
import polaris.models


class Migration(migrations.Migration):
    dependencies = [
        ("polaris", "0009_transaction_client_domain"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="distribution_seed",
            field=polaris.models.EncryptedTextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="paging_token",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="protocol",
            field=models.CharField(
                blank=True,
                choices=[("sep6", "sep6"), ("sep24", "sep24"), ("sep31", "sep31")],
                max_length=5,
                null=True,
            ),
        ),
    ]
