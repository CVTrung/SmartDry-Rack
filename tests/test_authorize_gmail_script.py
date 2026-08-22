import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.authorize_gmail import (
    GmailAuthorizationScriptError,
    authorize_notification_recipient,
)


class AuthorizeGmailScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            gmail=SimpleNamespace(
                recipient_email="fallback@example.com",
            ),
            weather_notifications=SimpleNamespace(
                device_id="device_001",
            ),
        )
        self.repository = MagicMock()

    def test_authorizes_configured_account_only(self) -> None:
        self.repository.get_account.return_value = {
            "device_id": "device_001",
            "gmail": "old@example.com",
        }
        self.repository.update_account.return_value = {
            "device_id": "device_001",
            "gmail": "new@example.com",
            "gmail_authorized": True,
        }
        answers = iter(["new@example.com", "yes"])

        account = authorize_notification_recipient(
            self.settings,
            self.repository,
            input_fn=lambda prompt: next(answers),
        )

        self.repository.get_account.assert_called_once_with(
            "device_001"
        )
        self.repository.update_account.assert_called_once_with(
            "device_001",
            gmail="new@example.com",
            gmail_authorized=True,
        )
        self.assertTrue(account["gmail_authorized"])

    def test_missing_configured_account_is_rejected(self) -> None:
        self.repository.get_account.return_value = None

        with self.assertRaisesRegex(
            GmailAuthorizationScriptError,
            "Account does not exist",
        ):
            authorize_notification_recipient(
                self.settings,
                self.repository,
            )

        self.repository.update_account.assert_not_called()

    def test_cancel_does_not_authorize_account(self) -> None:
        self.repository.get_account.return_value = {
            "device_id": "device_001",
            "gmail": "recipient@example.com",
        }
        answers = iter(["", "no"])

        account = authorize_notification_recipient(
            self.settings,
            self.repository,
            input_fn=lambda prompt: next(answers),
        )

        self.assertIsNone(account)
        self.repository.update_account.assert_not_called()

    @patch("scripts.authorize_gmail.FirestoreService")
    @patch("scripts.authorize_gmail.authorize_notification_recipient")
    @patch("scripts.authorize_gmail.authorize_gmail")
    @patch("scripts.authorize_gmail.get_settings")
    @patch("scripts.authorize_gmail.parse_arguments")
    def test_main_runs_sender_then_account_authorization(
        self,
        parse_arguments: MagicMock,
        get_settings: MagicMock,
        authorize_sender: MagicMock,
        authorize_account: MagicMock,
        firestore_class: MagicMock,
    ) -> None:
        from scripts.authorize_gmail import main

        parse_arguments.return_value = SimpleNamespace(force=False)
        settings = MagicMock()
        get_settings.return_value = settings
        authorize_sender.return_value = Path("gmail-token.json")
        authorize_account.return_value = {
            "device_id": "device_001"
        }

        main()

        authorize_sender.assert_called_once_with(
            settings.gmail,
            force=False,
        )
        authorize_account.assert_called_once_with(
            settings,
            firestore_class.return_value,
        )


if __name__ == "__main__":
    unittest.main()
