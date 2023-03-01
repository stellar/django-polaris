from django.db import migrations, models
import polaris.models


class Migration(migrations.Migration):
    dependencies = [
        ("polaris", "0002_auto_20200921_2135"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="asset", name="distribution_account_master_signer"
        ),
        migrations.RemoveField(model_name="asset", name="distribution_account_signers"),
        migrations.RemoveField(
            model_name="asset", name="distribution_account_thresholds"
        ),
    ]
