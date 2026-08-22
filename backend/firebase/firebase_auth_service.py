import re
from typing import Any

from firebase_admin import auth

from backend.firebase.firebase_app import get_firebase_app
from backend.firebase.firestore_service import (
    FirestoreService,
)

DEVICE_ID_PATTERN = re.compile(r"^[a-z0-9_-]+$")

class FirebaseAuthService:
    LOGIN_EMAIL_DOMAIN = "smartdry.local"

    def __init__(
        self,
        firestore_service: FirestoreService | None = None,
    ) -> None:
        self.app = get_firebase_app()

        self.firestore = (
            firestore_service
            if firestore_service is not None
            else FirestoreService()
        )

    @staticmethod
    def _validate_device_id(device_id: str) -> str:
        device_id = device_id.strip().lower()

        if not device_id:
            raise ValueError(
                "device_id must not be empty"
            )

        if not DEVICE_ID_PATTERN.fullmatch(device_id):
            raise ValueError(
                "device_id may only contain lowercase letters, "
                "numbers, hyphens, and underscores"
            )

        if len(device_id) > 128:
            raise ValueError(
                "device_id must not exceed 128 characters"
            )

        return device_id

    @staticmethod
    def _validate_password(password: str) -> str:
        if len(password) < 6:
            raise ValueError(
                "password must contain at least 6 characters"
            )

        return password

    @classmethod
    def get_login_email(
        cls,
        device_id: str,
    ) -> str:
        device_id = cls._validate_device_id(device_id)

        return f"{device_id}@{cls.LOGIN_EMAIL_DOMAIN}"

    def create_device_account(
        self,
        device_id: str,
        password: str,
        display_name: str,
        location_id: str,
        gmail: str,
        gmail_authorized: bool = False,
        enabled: bool = True,
    ) -> dict[str, Any]:
        device_id = self._validate_device_id(device_id)
        password = self._validate_password(password)

        login_email = self.get_login_email(device_id)

        user = auth.create_user(
            uid=device_id,
            email=login_email,
            password=password,
            display_name=display_name,
            disabled=not enabled,
            app=self.app,
        )

        try:
            account = self.firestore.create_account(
                device_id=device_id,
                display_name=display_name,
                location_id=location_id,
                gmail=gmail,
                gmail_authorized=gmail_authorized,
                enabled=enabled,
            )
        except Exception:
            auth.delete_user(
                user.uid,
                app=self.app,
            )
            raise

        return {
            "uid": user.uid,
            "login_email": login_email,
            "account": account,
        }

    def verify_id_token(
        self,
        id_token: str,
        check_revoked: bool = True,
    ) -> dict[str, Any]:
        id_token = id_token.strip()

        if not id_token:
            raise ValueError(
                "id_token must not be empty"
            )

        decoded_token = auth.verify_id_token(
            id_token,
            app=self.app,
            check_revoked=check_revoked,
        )

        device_id = decoded_token.get("uid")

        if not isinstance(device_id, str):
            raise PermissionError(
                "Token does not contain a valid uid"
            )

        if not self.firestore.account_is_enabled(device_id):
            raise PermissionError(
                "Device account is disabled"
            )

        return decoded_token

    def delete_device_account(
        self,
        device_id: str,
    ) -> None:
        device_id = self._validate_device_id(device_id)

        try:
            auth.delete_user(
                device_id,
                app=self.app,
            )
        except auth.UserNotFoundError:
            # A previous partial deletion may already have removed Auth.
            pass

        self.firestore.delete_account(device_id)

    def get_account_from_id_token(
        self,
        id_token: str,
    ) -> dict[str, Any]:
        decoded_token = self.verify_id_token(
            id_token,
            check_revoked=True,
        )

        device_id = decoded_token["uid"]
        account = self.firestore.get_account(device_id)

        if not account:
            raise PermissionError(
                "Device account does not exist"
            )

        if account.get("enabled") is not True:
            raise PermissionError(
                "Device account is disabled"
            )

        return {
            "device_id": device_id,
            "display_name": account.get("display_name", device_id),
            "gmail": account.get("gmail"),
            "gmail_authorized": (
                account.get("gmail_authorized") is True
            ),
            "enabled": True,
        }
