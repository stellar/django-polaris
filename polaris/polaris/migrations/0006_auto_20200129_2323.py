# Generated by Django 2.2.9 on 2020-01-29 23:23

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("polaris", "0005_auto_20200121_1852"),
    ]

    operations = [
        migrations.AlterField(
            model_name="asset", name="code", field=models.TextField(default="USD"),
        ),
        migrations.AlterField(
            model_name="asset",
            name="deposit_fee_fixed",
            field=models.DecimalField(
                blank=True, decimal_places=7, default=0, max_digits=30
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="deposit_fee_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                default=0,
                max_digits=30,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="deposit_max_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                default=10000000000000000000000,
                max_digits=30,
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="deposit_min_amount",
            field=models.DecimalField(
                blank=True, decimal_places=7, default=0, max_digits=30
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="withdrawal_fee_fixed",
            field=models.DecimalField(
                blank=True, decimal_places=7, default=0, max_digits=30
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="withdrawal_fee_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                default=0,
                max_digits=30,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="withdrawal_max_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                default=10000000000000000000000,
                max_digits=30,
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="withdrawal_min_amount",
            field=models.DecimalField(
                blank=True, decimal_places=7, default=0, max_digits=30
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="amount_fee",
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=30, null=True
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="amount_in",
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=30, null=True
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="amount_out",
            field=models.DecimalField(
                blank=True, decimal_places=7, max_digits=30, null=True
            ),
        ),
    ]
