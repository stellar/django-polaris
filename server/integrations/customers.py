from typing import Dict, Optional, List, Tuple
from logging import getLogger

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from rest_framework.request import Request
from stellar_sdk import MuxedAccount

from polaris.integrations import CustomerIntegration
from polaris.sep10.token import SEP10Token

from .sep24_kyc import send_confirmation_email
from ..models import PolarisUser, PolarisStellarAccount

logger = getLogger(__name__)


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
        self.optional_fields = ["photo_id_front", "photo_id_back"]
        self.accepted = {"status": "ACCEPTED"}
        self.needs_info = {"status": "NEEDS_INFO"}
        self.optional = {"optional": True}
        self.first_name = {
            "first_name": {
                "description": "first name of the customer",
                "type": "string",
            },
        }
        self.last_name = {
            "last_name": {
                "description": "last name of the customer",
                "type": "string",
            },
        }
        self.email_address = {
            "email_address": {
                "description": "email address of the customer",
                "type": "string",
            },
        }
        self.photo_id_front = {
            "photo_id_front": {
                "description": "Image of front of user's photo ID or passport",
                "type": "binary",
                "optional": True,
            },
        }
        self.photo_id_back = {
            "photo_id_back": {
                "description": "Image of back of user's photo ID or passport",
                "type": "binary",
                "optional": True,
            },
        }
        self.bank_account_number = {
            "bank_account_number": {
                "description": "bank account number of the customer",
                "type": "string",
            },
        }
        self.bank_number = {
            "bank_number": {
                "description": "routing number of the customer",
                "type": "string",
            },
        }

    def get(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> Dict:
        user = self._get_user(
            params.get("id"),
            params.get("account"),
            params.get("memo"),
            params.get("memo_type"),
        )

        response_data = {}
        if not user:
            if params.get("type") in ["sep6-deposit", "sep31-sender"]:
                response_data.update(self.needs_info)
                response_data["fields"] = {
                    **self.first_name,
                    **self.last_name,
                    **self.email_address,
                    **self.photo_id_front,
                    **self.photo_id_back,
                }
                return response_data
            elif params.get("type") in [None, "sep6-withdraw", "sep31-receiver"]:
                response_data.update(self.needs_info)
                response_data["fields"] = {
                    **self.first_name,
                    **self.last_name,
                    **self.email_address,
                    **self.bank_account_number,
                    **self.bank_number,
                    **self.photo_id_front,
                    **self.photo_id_back,
                }
                return response_data
            else:
                raise ValueError(
                    _("invalid 'type'. see /info response for valid values.")
                )

        first_name_obj = self.first_name.copy()
        first_name_obj["first_name"].update(**self.accepted)

        last_name_obj = self.last_name.copy()
        last_name_obj["last_name"].update(**self.accepted)

        email_obj = self.email_address.copy()
        email_obj["email_address"].update(**self.accepted)

        response_data = {
            "id": str(user.id),
            "provided_fields": {**first_name_obj, **last_name_obj, **email_obj},
            "fields": {},
        }

        if user.bank_account_number:
            bank_account_number_obj = self.bank_account_number.copy()
            bank_account_number_obj["bank_account_number"].update(**self.accepted)
            response_data["provided_fields"].update(**bank_account_number_obj)
        elif params.get("type") in [None, "sep6-withdraw", "sep31-receiver"]:
            response_data["fields"].update(**self.bank_account_number)

        if user.bank_number:
            bank_number_obj = self.bank_number.copy()
            bank_number_obj["bank_account_number"].update(**self.accepted)
            response_data["provided_fields"].update(**bank_number_obj)
        elif params.get("type") in [None, "sep6-withdraw", "sep31-receiver"]:
            response_data["fields"].update(**self.bank_number)

        if user.photo_id_front_provided:
            photo_id_front_obj = self.photo_id_front.copy()
            photo_id_front_obj["photo_id_front"].update(**self.accepted)
            response_data["provided_fields"].update(**photo_id_front_obj)
        else:
            response_data["fields"].update(**self.photo_id_front)

        if user.photo_id_back_provided:
            photo_id_back_obj = self.photo_id_back.copy()
            photo_id_back_obj["photo_id_back"].update(**self.accepted)
            response_data["provided_fields"].update(**photo_id_back_obj)
        else:
            response_data["fields"].update(**self.photo_id_back)

        if params.get("type") in ["sep6-deposit", "sep31-sender"]:
            response_data.update(**self.accepted)
        elif params.get("type") in [None, "sep6-withdraw", "sep31-receiver"]:
            if all([self.bank_account_number, self.bank_number]):
                response_data.update(**self.accepted)
            else:
                response_data.update(**self.needs_info)
        else:
            raise ValueError(_("invalid 'type'. see /info response for valid values."))

        return response_data

    def put(
        self, token: SEP10Token, request: Request, params: Dict, *args, **kwargs
    ) -> str:
        user = self._get_user(
            params.get("id"),
            params.get("account"),
            params.get("memo"),
            params.get("memo_type"),
        )
        if not user:
            # email_address is a secondary ID
            if "email_address" not in params:
                raise ValueError(
                    "SEP-9 fields were not passed for new customer. "
                    "'first_name', 'last_name', and 'email_address' are required."
                )
            # find existing user by previously-specified email
            user = PolarisUser.objects.filter(email=params["email_address"]).first()
            if user:
                stellar_account, muxed_account = self._get_stellar_and_muxed_account(
                    params.get("account")
                )
                account = PolarisStellarAccount.objects.create(
                    user=user,
                    account=stellar_account,
                    muxed_account=muxed_account,
                    memo=params["memo"],
                    memo_type=params["memo_type"],
                )
                # send_confirmation_email(user, account)
            else:
                user, account = self.create_new_user(params)
                # send_confirmation_email(user, account)

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
        user.photo_id_front_provided = (
            bool(params.get("photo_id_front")) or user.photo_id_front_provided
        )
        user.photo_id_back_provided = (
            bool(params.get("photo_id_back")) or user.photo_id_back_provided
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
        stellar_account, muxed_account = self._get_stellar_and_muxed_account(account)
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

    def create_new_user(self, params):
        if not all(f in params for f in ["first_name", "last_name", "email_address"]):
            raise ValueError(
                "SEP-9 fields were not passed for new customer. "
                "'first_name', 'last_name', and 'email_address' are required."
            )
        stellar_account, muxed_account = self._get_stellar_and_muxed_account(
            params.get("account")
        )
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

    def _get_user(
        self, pid: str, account: str, memo: str, memo_type: str
    ) -> Optional[PolarisUser]:
        user = None
        if pid:
            user = PolarisUser.objects.filter(id=pid).first()
            if not user:
                raise ObjectDoesNotExist(_("customer not found"))
        elif account:
            stellar_account, muxed_account = self._get_stellar_and_muxed_account(
                account
            )
            paccount = PolarisStellarAccount.objects.filter(
                account=stellar_account,
                muxed_account=muxed_account,
                memo=memo,
                memo_type=memo_type,
            ).first()
            user = paccount.user if paccount else None
        return user

    def _get_stellar_and_muxed_account(self, account: str) -> Tuple[str, str]:
        if account.startswith("M"):
            stellar_account = MuxedAccount.from_account(account).account_id
            muxed_account = account
        else:
            stellar_account = account
            muxed_account = None
        return stellar_account, muxed_account
