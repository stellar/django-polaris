from django.db import migrations, models
import polaris.models


class Migration(migrations.Migration):

    dependencies = [
        ("polaris", "0002_auto_20200921_2135"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="updated_at",
            field=models.DateTimeField(default=polaris.models.utc_now),
        ),
    ]
