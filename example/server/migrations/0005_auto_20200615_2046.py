# Generated by Django 2.2.12 on 2020-06-15 20:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    SEP31 allows anchors to deposit assets directly to a user's off-chain account.
    This violates the assumption that every PolarisUserTransaction will have a stellar_account.

    Therefore, we add a user FK to PolarisUserTransaction and make its account FK column nullable.
    Additionally, PolarisUserTransaction.transaction_id is changed to TextField instead of an FK,
    since at time of creation the Transaction object does not exist.
    """

    dependencies = [
        ("server", "0004_auto_20200427_2302"),
    ]

    operations = [
        migrations.RenameField(
            model_name="polarisusertransaction",
            old_name="transaction",
            new_name="temp_transaction",
        ),
        migrations.AddField(
            model_name="polarisusertransaction",
            name="transaction_id",
            field=models.TextField(db_index=True, default="id"),
            preserve_default=False,
        ),
        migrations.RunSQL(
            "UPDATE server_polarisusertransaction SET transaction_id = temp_transaction_id"
        ),
        migrations.RemoveField(
            model_name="polarisusertransaction", name="temp_transaction",
        ),
        migrations.AddField(
            model_name="polarisusertransaction",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="server.PolarisUser",
            ),
        ),
        migrations.AlterField(
            model_name="polarisusertransaction",
            name="account",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="server.PolarisStellarAccount",
            ),
        ),
    ]
