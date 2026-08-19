import base64
import unittest

from email import message_from_bytes
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from backend.config import GmailSettings
from backend.notifications.gmail_service import (
    GmailAuthorizationError,
    GmailDisabledError,
    GmailNotificationService,
    GmailSendError,
)


class GmailNotificationServiceTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.settings = GmailSettings(
            enabled=True,
            sender_email="sender@example.com",
            recipient_email="recipient@example.com",
            credentials_path=Path(
                "secrets/gmail-credentials.json"
            ),
            token_path=Path(
                "secrets/gmail-token.json"
            ),
            max_retry_attempts=3,
        )

        self.service = GmailNotificationService(
            self.settings
        )

        self.gmail_client = MagicMock()
        self.service._client = self.gmail_client

        self.send_request = (
            self.gmail_client
            .users.return_value
            .messages.return_value
            .send
        )

        self.execute = (
            self.send_request
            .return_value
            .execute
        )

    def test_sends_email_and_returns_message_id(
        self,
    ) -> None:
        self.execute.return_value = {
            "id": "gmail_message_001",
        }

        result = self.service.send_email(
            subject="SmartDry rain warning",
            body="Rain is expected within 120 minutes.",
        )

        self.assertEqual(
            result,
            "gmail_message_001",
        )

        self.send_request.assert_called_once()
        self.execute.assert_called_once_with(
            num_retries=2
        )

        call_arguments = (
            self.send_request.call_args.kwargs
        )

        self.assertEqual(
            call_arguments["userId"],
            "me",
        )

        raw_message = call_arguments["body"]["raw"]

        decoded_bytes = base64.urlsafe_b64decode(
            raw_message.encode("utf-8")
        )

        email = message_from_bytes(decoded_bytes)

        self.assertEqual(
            email["From"],
            "sender@example.com",
        )
        self.assertEqual(
            email["To"],
            "recipient@example.com",
        )
        self.assertEqual(
            email["Subject"],
            "SmartDry rain warning",
        )

        self.assertIn(
            "Rain is expected within 120 minutes.",
            email.get_payload(),
        )

    def test_accepts_custom_recipient(
        self,
    ) -> None:
        self.execute.return_value = {
            "id": "gmail_message_002",
        }

        self.service.send_email(
            subject="SmartDry warning",
            body="Rain detected.",
            recipient_email="owner@example.com",
        )

        raw_message = (
            self.send_request
            .call_args.kwargs["body"]["raw"]
        )

        decoded_bytes = base64.urlsafe_b64decode(
            raw_message.encode("utf-8")
        )

        email = message_from_bytes(decoded_bytes)

        self.assertEqual(
            email["To"],
            "owner@example.com",
        )

    def test_custom_recipient_does_not_require_fallback(
        self,
    ) -> None:
        settings = GmailSettings(
            enabled=True,
            sender_email="sender@example.com",
            recipient_email=None,
            credentials_path=Path("unused.json"),
            token_path=Path("unused-token.json"),
            max_retry_attempts=3,
        )
        service = GmailNotificationService(settings)
        service._client = self.gmail_client
        self.execute.return_value = {
            "id": "gmail_message_003",
        }

        result = service.send_email(
            subject="SmartDry warning",
            body="Rain detected.",
            recipient_email="owner@gmail.com",
        )

        self.assertEqual(result, "gmail_message_003")

    def test_missing_account_and_fallback_recipient_fails(
        self,
    ) -> None:
        settings = GmailSettings(
            enabled=True,
            sender_email="sender@example.com",
            recipient_email=None,
            credentials_path=Path("unused.json"),
            token_path=Path("unused-token.json"),
            max_retry_attempts=3,
        )
        service = GmailNotificationService(settings)

        with self.assertRaisesRegex(
            GmailAuthorizationError,
            "recipient email is missing",
        ):
            service.send_email(
                subject="SmartDry warning",
                body="Rain detected.",
            )

    def test_rejects_disabled_gmail(
        self,
    ) -> None:
        settings = GmailSettings(
            enabled=False,
            sender_email=None,
            recipient_email=None,
            credentials_path=None,
            token_path=None,
            max_retry_attempts=3,
        )

        service = GmailNotificationService(settings)

        with self.assertRaises(GmailDisabledError):
            service.send_email(
                subject="Test",
                body="Test message",
            )

    def test_rejects_invalid_recipient(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.send_email(
                subject="Test",
                body="Test message",
                recipient_email="invalid-address",
            )

        self.send_request.assert_not_called()

    def test_rejects_empty_subject(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.send_email(
                subject="",
                body="Test message",
            )

        self.send_request.assert_not_called()

    def test_rejects_subject_with_newline(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.send_email(
                subject="Warning\nBcc: attacker@example.com",
                body="Test message",
            )

        self.send_request.assert_not_called()

    def test_rejects_empty_body(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.send_email(
                subject="Test",
                body="",
            )

        self.send_request.assert_not_called()

    def test_raises_when_message_id_is_missing(
        self,
    ) -> None:
        self.execute.return_value = {}

        with self.assertRaises(GmailSendError):
            self.service.send_email(
                subject="Test",
                body="Test message",
            )

    def test_converts_http_error_to_send_error(
        self,
    ) -> None:
        response = MagicMock()
        response.status = 400
        response.reason = "Bad Request"

        api_error = HttpError(
            response,
            b'{"error": {"message": "Invalid message"}}',
        )

        self.execute.side_effect = api_error

        with self.assertRaises(GmailSendError):
            self.service.send_email(
                subject="Test",
                body="Test message",
            )

    def test_missing_token_raises_authorization_error(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            settings = GmailSettings(
                enabled=True,
                sender_email="sender@example.com",
                recipient_email="recipient@example.com",
                credentials_path=Path(
                    directory
                ) / "credentials.json",
                token_path=Path(
                    directory
                ) / "missing-token.json",
                max_retry_attempts=3,
            )

            service = GmailNotificationService(
                settings
            )

            with self.assertRaises(
                GmailAuthorizationError
            ):
                service._load_credentials()

    def test_refreshes_expired_credentials(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            token_path = (
                Path(directory) / "token.json"
            )
            token_path.write_text(
                "{}",
                encoding="utf-8",
            )

            settings = GmailSettings(
                enabled=True,
                sender_email="sender@example.com",
                recipient_email="recipient@example.com",
                credentials_path=(
                    Path(directory) / "credentials.json"
                ),
                token_path=token_path,
                max_retry_attempts=3,
            )

            service = GmailNotificationService(
                settings
            )

            credentials = MagicMock()
            credentials.expired = True
            credentials.refresh_token = (
                "refresh-token"
            )
            credentials.valid = True

            with (
                patch(
                    (
                        "backend.notifications."
                        "gmail_service.Credentials."
                        "from_authorized_user_file"
                    ),
                    return_value=credentials,
                ),
                patch(
                    (
                        "backend.notifications."
                        "gmail_service.Request"
                    )
                ) as request_class,
                patch.object(
                    service,
                    "_save_credentials",
                ) as save_credentials,
            ):
                result = service._load_credentials()

            self.assertIs(
                result,
                credentials,
            )

            credentials.refresh.assert_called_once_with(
                request_class.return_value
            )

            save_credentials.assert_called_once_with(
                credentials,
                token_path,
            )

    def test_refresh_failure_becomes_authorization_error(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            token_path = (
                Path(directory) / "token.json"
            )
            token_path.write_text(
                "{}",
                encoding="utf-8",
            )

            settings = GmailSettings(
                enabled=True,
                sender_email="sender@example.com",
                recipient_email="recipient@example.com",
                credentials_path=(
                    Path(directory) / "credentials.json"
                ),
                token_path=token_path,
                max_retry_attempts=3,
            )

            service = GmailNotificationService(
                settings
            )

            credentials = MagicMock()
            credentials.expired = True
            credentials.refresh_token = (
                "refresh-token"
            )
            credentials.refresh.side_effect = (
                RefreshError(
                    "Refresh failed"
                )
            )

            with patch(
                (
                    "backend.notifications."
                    "gmail_service.Credentials."
                    "from_authorized_user_file"
                ),
                return_value=credentials,
            ):
                with self.assertRaises(
                    GmailAuthorizationError
                ):
                    service._load_credentials()


if __name__ == "__main__":
    unittest.main()
