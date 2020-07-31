from django.db import migrations
from django.db.models import Q, F


def migrate_memo_values(apps, schema_editor):
    Transaction = apps.get_model("polaris", "Transaction")
    deposit_null = Q(deposit_memo__isnull=True)
    send_not_null = Q(deposit_memo__isnull=False)
    withdraw_not_null = Q(withdraw_memo__isnull=False)
    Transaction.objects.filter(deposit_null & send_not_null).update(
        deposit_memo=F("send_memo"), deposit_memo_type=F("send_memo_type")
    )
    Transaction.objects.filter(deposit_null & withdraw_not_null).update(
        deposit_memo=F("withdraw_memo"), deposit_memo_type=F("withdraw_memo_type")
    )


def merge_receiving_accounts(apps, schema_editor):
    Transaction = apps.get_model("polaris", "Transaction")
    Transaction.objects.filter(withdraw_anchor_account__isnull=False).update(
        send_anchor_account=F("withdraw_anchor_account")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("polaris", "0016_auto_20200610_2321"),
    ]

    operations = [
        migrations.RunPython(migrate_memo_values),
        migrations.RunPython(merge_receiving_accounts),
    ]
