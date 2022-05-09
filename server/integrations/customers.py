from typing import Dict, Optional, List

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from rest_framework.request import Request
from stellar_sdk import MuxedAccount

from polaris.integrations import CustomerIntegration
from polaris.sep10.token import SEP10Token

from .sep24_kyc import send_confirmation_email
from ..models import PolarisUser, PolarisStellarAccount


class MyCustomerIntegration(CustomerIntegration):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.required_fields = [
            "account",
            "first_name",
            "last_name",
            "email_address",
            "bank_account_number",
            "bank_number",
        ]
        self.accepted = {"status": "ACCEPTED"}
        self.needs_basic_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                },
            },
        }
        self.needs_bank_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "bank_account_number": {
                    "description": "bank account number of the customer",
                    "type": "string",
                },
                "bank_number": {
                    "description": "routing number of the customer",
                    "type": "string",
                },
            },
        }
        self.needs_all_info = {
            "status": "NEEDS_INFO",
            "fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                },
                "bank_account_number": {
                    "description": "bank account number of the customer",
                    "type": "string",
                },
                "bank_number": {
                    "description": "routing number of the customer",
                    "type": "string",
                },
            },
        }

    def get(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> Dict:
        user = None
        if params.get("id"):
            user = PolarisUser.objects.filter(id=params["id"]).first()
            if not user:
                raise ObjectDoesNotExist(_("customer not found"))
        elif params.get("account"):
            if params["account"].startswith("M"):
                stellar_account = MuxedAccount.from_account(
                    params["account"]
                ).account_id
                muxed_account = params["account"]
            else:
                stellar_account = params["account"]
                muxed_account = None
            account = PolarisStellarAccount.objects.filter(
                account=stellar_account,
                muxed_account=muxed_account,
                memo=params.get("memo"),
                memo_type=params.get("memo_type"),
            ).first()
            user = account.user if account else None

        if not user:
            if params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]:
                return self.needs_basic_info
            elif params.get("type") in [None, "sep6-withdraw"]:
                return self.needs_all_info
            else:
                raise ValueError(
                    _("invalid 'type'. see /info response for valid values.")
                )

        response_data = {"id": str(user.id)}
        basic_info_accepted = {
            "provided_fields": {
                "first_name": {
                    "description": "first name of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
                "last_name": {
                    "description": "last name of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
                "email_address": {
                    "description": "email address of the customer",
                    "type": "string",
                    "status": "ACCEPTED",
                },
            }
        }
        if (user.bank_number and user.bank_account_number) or (
            params.get("type") in ["sep6-deposit", "sep31-sender", "sep31-receiver"]
        ):
            response_data.update(self.accepted)
            response_data.update(basic_info_accepted)
            if user.bank_number and user.bank_account_number:
                response_data["provided_fields"].update(
                    {
                        "bank_account_number": {
                            "description": "bank account number of the customer",
                            "type": "string",
                            "status": "ACCEPTED",
                        },
                        "bank_number": {
                            "description": "routing number of the customer",
                            "type": "string",
                            "status": "ACCEPTED",
                        },
                    }
                )
        elif params.get("type") in [None, "sep6-withdraw"]:
            response_data.update(basic_info_accepted)
            response_data.update(self.needs_bank_info)
        else:
            raise ValueError(_("invalid 'type'. see /info response for valid values."))
        return response_data

    def put(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> str:
        if params.get("id"):
            user = PolarisUser.objects.filter(id=params["id"]).first()
            if not user:
                raise ObjectDoesNotExist("could not identify user customer 'id'")
        else:
            if params["account"].startswith("M"):
                stellar_account = MuxedAccount.from_account(
                    params["account"]
                ).account_id
                muxed_account = params["account"]
            else:
                stellar_account = params["account"]
                muxed_account = None
            account = PolarisStellarAccount.objects.filter(
                account=stellar_account,
                muxed_account=muxed_account,
                memo=params.get("memo"),
                memo_type=params.get("memo_type"),
            ).first()
            if not account:
                # email_address is a secondary ID
                if "email_address" not in params:
                    raise ValueError(
                        "SEP-9 fields were not passed for new customer. "
                        "'first_name', 'last_name', and 'email_address' are required."
                    )
                # find existing user by previously-specified email
                user = PolarisUser.objects.filter(email=params["email_address"]).first()
                if user:
                    account = PolarisStellarAccount.objects.create(
                        user=user,
                        account=stellar_account,
                        muxed_account=muxed_account,
                        memo=params["memo"],
                        memo_type=params["memo_type"],
                    )
                    send_confirmation_email(user, account)
                else:
                    user, account = self.create_new_user(params)
                    send_confirmation_email(user, account)
            else:
                user = account.user

        if (
            user.email != params.get("email_address")
            and PolarisUser.objects.filter(email=params.get("email_address")).exists()
        ):
            raise ValueError("email_address is taken")

        user.email = params.get("email_address") or user.email
        user.first_name = params.get("first_name") or user.first_name
        user.last_name = params.get("last_name") or user.last_name
        user.bank_number = params.get("bank_number") or user.bank_number
        user.bank_account_number = (
            params.get("bank_account_number") or user.bank_account_number
        )
        user.save()

        return str(user.id)

    def delete(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        memo: Optional[str],
        memo_type: Optional[str],
        *args,
        **kwargs,
    ):
        if account.startswith("M"):
            stellar_account = MuxedAccount.from_account(account).account_id
            muxed_account = account
        else:
            stellar_account = account
            muxed_account = None
        qparams = {
            "account": stellar_account,
            "muxed_account": muxed_account,
            "memo": memo,
            "memo_type": memo_type,
        }
        account = PolarisStellarAccount.objects.filter(**qparams).first()
        if not account:
            raise ObjectDoesNotExist()
        account.user.delete()

    @staticmethod
    def create_new_user(params):
        if not all(f in params for f in ["first_name", "last_name", "email_address"]):
            raise ValueError(
                "SEP-9 fields were not passed for new customer. "
                "'first_name', 'last_name', and 'email_address' are required."
            )
        if params["account"].startswith("M"):
            stellar_account = MuxedAccount.from_account(params["account"]).account_id
            muxed_account = params["account"]
        else:
            stellar_account = params["account"]
            muxed_account = None
        user = PolarisUser.objects.create(
            first_name=params["first_name"],
            last_name=params["last_name"],
            email=params["email_address"],
            bank_number=params.get("bank_number"),
            bank_account_number=params.get("bank_account_number"),
        )
        account = PolarisStellarAccount.objects.create(
            user=user,
            account=stellar_account,
            muxed_account=muxed_account,
            memo=params.get("memo"),
            memo_type=params.get("memo_type"),
        )
        return user, account

    def more_info_url(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        *args: List,
        memo: Optional[int] = None,
        **kwargs: Dict,
    ) -> str:
        raise NotImplementedError()

    def callback(
        self,
        token: SEP10Token,
        request: Request,
        params: Dict,
        *args: List,
        **kwargs: Dict,
    ):
        raise NotImplementedError()

    def put_verification(
        self,
        token: SEP10Token,
        request: Request,
        account: str,
        params: Dict,
        *args: List,
        **kwargs: Dict,
    ) -> Dict:
        raise NotImplementedError()
