import unittest

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from backend.config import GmailSettings
from backend.models import (
    EmailContent,
    EmailStatus,
    WeatherAlert,
)
from backend.notifications.gmail_service import (
    GmailSendError,
)
from backend.notifications.weather_notification_service import (
    WeatherNotificationService,
)


class WeatherNotificationServiceTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.gmail_settings = GmailSettings(
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

        self.repository = MagicMock()
        self.gmail_service = MagicMock()
        self.email_formatter = MagicMock()

        self.service = WeatherNotificationService(
            repository=self.repository,
            gmail_service=self.gmail_service,
            email_formatter=self.email_formatter,
            gmail_settings=self.gmail_settings,
        )

        self.now = datetime(
            2026,
            8,
            16,
            10,
            0,
            tzinfo=timezone.utc,
        )

        self.alert = WeatherAlert.current_rain(
            device_id="device_001",
            location_id="location_hcm",
            observed_at=self.now,
            rain_started_at=self.now,
            condition="Rain",
            rain_amount_mm=1.5,
        )

        self.email_content = EmailContent(
            subject="[SmartDry] Rain detected now",
            body="Rain is happening now.",
        )

    def test_stores_before_sending_email(
        self,
    ) -> None:
        events: list[str] = []

        def create_notification(
            *args,
            **kwargs,
        ) -> bool:
            events.append("notification_created")
            return True

        def send_email(
            *args,
            **kwargs,
        ) -> str:
            events.append("gmail_sent")
            return "gmail_message_001"

        def mark_email_sent(
            *args,
            **kwargs,
        ) -> None:
            events.append("status_updated")

        self.repository.create_notification.side_effect = (
            create_notification
        )
        self.gmail_service.send_email.side_effect = (
            send_email
        )
        self.repository.mark_email_sent.side_effect = (
            mark_email_sent
        )

        self.email_formatter.format.return_value = (
            self.email_content
        )

        result = self.service.notify(
            self.alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.assertEqual(
            events,
            [
                "notification_created",
                "gmail_sent",
                "status_updated",
            ],
        )

        self.assertTrue(result.created)
        self.assertEqual(
            result.email_status,
            EmailStatus.SENT,
        )
        self.assertEqual(
            result.gmail_message_id,
            "gmail_message_001",
        )

        self.repository.create_notification.assert_called_once_with(
            self.alert,
            email_status=EmailStatus.PENDING,
        )

        self.email_formatter.format.assert_called_once_with(
            self.alert,
            device_name="Laundry Rack",
            location_name="Ho Chi Minh City",
            timezone_name="Asia/Ho_Chi_Minh",
        )

        self.gmail_service.send_email.assert_called_once_with(
            subject=self.email_content.subject,
            body=self.email_content.body,
        )

        self.repository.mark_email_sent.assert_called_once_with(
            device_id="device_001",
            notification_id=self.alert.alert_id,
            gmail_message_id="gmail_message_001",
        )

    def test_duplicate_notification_skips_email(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            False
        )

        result = self.service.notify(self.alert)

        self.assertFalse(result.created)
        self.assertEqual(
            result.email_status,
            EmailStatus.SKIPPED,
        )

        self.email_formatter.format.assert_not_called()
        self.gmail_service.send_email.assert_not_called()
        self.repository.mark_email_sent.assert_not_called()
        self.repository.mark_email_failed.assert_not_called()

    def test_disabled_gmail_stores_notification(
        self,
    ) -> None:
        disabled_settings = GmailSettings(
            enabled=False,
            sender_email=None,
            recipient_email=None,
            credentials_path=None,
            token_path=None,
            max_retry_attempts=3,
        )

        service = WeatherNotificationService(
            repository=self.repository,
            gmail_service=self.gmail_service,
            email_formatter=self.email_formatter,
            gmail_settings=disabled_settings,
        )

        self.repository.create_notification.return_value = (
            True
        )

        result = service.notify(self.alert)

        self.assertTrue(result.created)
        self.assertEqual(
            result.email_status,
            EmailStatus.SKIPPED,
        )

        self.repository.create_notification.assert_called_once_with(
            self.alert,
            email_status=EmailStatus.SKIPPED,
        )

        self.email_formatter.format.assert_not_called()
        self.gmail_service.send_email.assert_not_called()

    def test_unauthorized_account_email_is_skipped(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            True
        )

        result = self.service.notify(
            self.alert,
            recipient_email="owner@gmail.com",
            email_authorized=False,
        )

        self.assertEqual(
            result.email_status,
            EmailStatus.SKIPPED,
        )
        self.repository.create_notification.assert_called_once_with(
            self.alert,
            email_status=EmailStatus.SKIPPED,
        )
        self.email_formatter.format.assert_not_called()
        self.gmail_service.send_email.assert_not_called()

    def test_sends_to_authorized_account_email(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            True
        )
        self.email_formatter.format.return_value = (
            self.email_content
        )
        self.gmail_service.send_email.return_value = (
            "gmail_message_002"
        )

        result = self.service.notify(
            self.alert,
            recipient_email="owner@gmail.com",
            email_authorized=True,
        )

        self.assertEqual(
            result.email_status,
            EmailStatus.SENT,
        )
        self.gmail_service.send_email.assert_called_once_with(
            subject=self.email_content.subject,
            body=self.email_content.body,
            recipient_email="owner@gmail.com",
        )

    def test_gmail_failure_is_recorded(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            True
        )

        self.email_formatter.format.return_value = (
            self.email_content
        )

        self.gmail_service.send_email.side_effect = (
            GmailSendError(
                "Gmail API returned HTTP 429"
            )
        )

        result = self.service.notify(self.alert)

        self.assertTrue(result.created)
        self.assertEqual(
            result.email_status,
            EmailStatus.FAILED,
        )
        self.assertEqual(
            result.error,
            "Gmail API returned HTTP 429",
        )

        self.repository.mark_email_failed.assert_called_once_with(
            device_id="device_001",
            notification_id=self.alert.alert_id,
            error_message=(
                "Gmail API returned HTTP 429"
            ),
        )

        self.repository.mark_email_sent.assert_not_called()

    def test_formatter_failure_is_recorded(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            True
        )

        self.email_formatter.format.side_effect = (
            ValueError("Unknown timezone")
        )

        result = self.service.notify(self.alert)

        self.assertEqual(
            result.email_status,
            EmailStatus.FAILED,
        )
        self.assertEqual(
            result.error,
            "Unknown timezone",
        )

        self.repository.mark_email_failed.assert_called_once_with(
            device_id="device_001",
            notification_id=self.alert.alert_id,
            error_message="Unknown timezone",
        )

        self.gmail_service.send_email.assert_not_called()

    def test_failure_status_error_does_not_escape(
        self,
    ) -> None:
        self.repository.create_notification.return_value = (
            True
        )

        self.email_formatter.format.return_value = (
            self.email_content
        )

        self.gmail_service.send_email.side_effect = (
            GmailSendError("Gmail unavailable")
        )

        self.repository.mark_email_failed.side_effect = (
            RuntimeError("Firestore unavailable")
        )

        result = self.service.notify(self.alert)

        self.assertEqual(
            result.email_status,
            EmailStatus.FAILED,
        )
        self.assertEqual(
            result.error,
            "Gmail unavailable",
        )

    def test_storage_failure_prevents_email(
        self,
    ) -> None:
        self.repository.create_notification.side_effect = (
            RuntimeError("Firestore unavailable")
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Firestore unavailable",
        ):
            self.service.notify(self.alert)

        self.email_formatter.format.assert_not_called()
        self.gmail_service.send_email.assert_not_called()

    def test_long_error_is_truncated(
        self,
    ) -> None:
        long_error = RuntimeError("x" * 1000)

        result = self.service._safe_error_message(
            long_error
        )

        self.assertEqual(len(result), 500)


if __name__ == "__main__":
    unittest.main()
