# Generated by Django 3.2.8 on 2021-10-20 22:39

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("polaris", "0013_auto_20211011_1956"),
        ("server", "0007_auto_20210921_2005"),
    ]

    operations = [
        migrations.CreateModel(
            name="OffChainAssetExtra",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "fee_fixed",
                    models.DecimalField(decimal_places=7, default=0, max_digits=30),
                ),
                ("fee_percent", models.PositiveIntegerField(default=0)),
                (
                    "offchain_asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="polaris.offchainasset",
                    ),
                ),
            ],
        ),
    ]
