from decimal import Decimal
from typing import Optional, Dict

from django.utils.translation import gettext as _
from rest_framework.request import Request

from polaris.integrations import SEP31ReceiverIntegration
from polaris.models import Asset, Transaction
from polaris.sep10.token import SEP10Token

from ..models import PolarisUser, PolarisUserTransaction


class MySEP31ReceiverIntegration(SEP31ReceiverIntegration):
    def info(
        self,
        request: Request,
        asset: Asset,
        lang: Optional[str] = None,
        *args,
        **kwargs,
    ):
        return {
            "sep12": {
                "sender": {
                    "types": {
                        "sep31-sender": {
                            "description": "the basic type for sending customers"
                        }
                    }
                },
                "receiver": {
                    "types": {
                        "sep31-receiver": {
                            "description": "the basic type for receiving customers"
                        }
                    }
                },
            },
            "fields": {
                "transaction": {
                    "routing_number": {
                        "description": "routing number of the destination bank account"
                    },
                    "account_number": {
                        "description": "bank account number of the destination"
                    },
                },
            },
        }

    def process_post_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ) -> Optional[Dict]:
        _ = params.get("sender_id")  # not actually used
        receiver_id = params.get("receiver_id")
        transaction_fields = params.get("fields", {}).get("transaction")
        for field, val in transaction_fields.items():
            if not isinstance(val, str):
                return {"error": f"'{field}'" + _(" is not of type str")}

        receiving_user = PolarisUser.objects.filter(id=receiver_id).first()
        if not receiving_user:
            return {"error": "customer_info_needed", "type": "sep31-receiver"}

        elif not (receiving_user.bank_account_number and receiving_user.bank_number):
            receiving_user.bank_account_number = transaction_fields["account_number"]
            receiving_user.bank_number = transaction_fields["routing_number"]
            receiving_user.save()

        transaction.amount_fee = round(
            transaction.asset.send_fee_fixed
            + (
                transaction.asset.send_fee_percent
                / Decimal(100)
                * transaction.amount_in
            ),
            transaction.asset.significant_decimals,
        )
        transaction.fee_asset = params["asset"].asset_identification_format
        if not transaction.quote:
            transaction.amount_out = round(
                transaction.amount_in - transaction.amount_fee,
                transaction.asset.significant_decimals,
            )
        else:
            transaction.quote.save()
        transaction.save()

        PolarisUserTransaction.objects.create(
            user=receiving_user, transaction_id=transaction.id
        )

    def process_patch_request(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        transaction: Transaction,
        *args,
        **kwargs,
    ):
        info_fields = params.get("fields", {})
        transaction_fields = info_fields.get("transaction", {})
        if not isinstance(transaction_fields, dict):
            raise ValueError(_("'transaction' value must be an object"))
        possible_fields = set()
        for obj in self.info(request, transaction.asset)["fields"].values():
            possible_fields.union(obj.keys())
        update_fields = list(transaction_fields.keys())
        if not update_fields:
            raise ValueError(_("No fields provided"))
        elif any(f not in possible_fields for f in update_fields):
            raise ValueError(_("unexpected fields provided"))
        elif not all(isinstance(update_fields[f], str) for f in update_fields):
            raise ValueError(_("field values must be strings"))
        user = (
            PolarisUserTransaction.objects.filter(transaction_id=transaction.id)
            .first()
            .user
        )
        if "routing_number" in update_fields:
            user.bank_number = transaction_fields["routing_number"]
        elif "account_number" in update_fields:
            user.bank_account_number = transaction_fields["account_number"]
        user.save()

    def valid_sending_anchor(
        self, token: SEP10Token, request: Request, public_key: str, *args, **kwargs
    ) -> bool:
        # A real anchor would check if public_key belongs to a partner anchor
        return True
