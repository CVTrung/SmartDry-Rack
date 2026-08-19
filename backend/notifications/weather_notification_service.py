import logging

from typing import Protocol

from backend.config import GmailSettings
from backend.models import (
    EmailStatus,
    NotificationResult,
    WeatherAlert,
)
from backend.notifications.gmail_service import (
    GmailNotificationError,
    GmailNotificationService,
)
from backend.notifications.weather_email_formatter import (
    WeatherEmailFormatter,
)


logger = logging.getLogger(__name__)


class NotificationRepository(Protocol):
    def create_notification(
        self,
        alert: WeatherAlert,
        *,
        email_status: EmailStatus,
    ) -> bool:
        """
        Create a notification if it does not exist.

        Return True when created.
        Return False when the alert ID already exists.
        """

    def mark_email_sent(
        self,
        *,
        device_id: str,
        notification_id: str,
        gmail_message_id: str,
    ) -> None:
        """Mark a notification email as sent."""

    def mark_email_failed(
        self,
        *,
        device_id: str,
        notification_id: str,
        error_message: str,
    ) -> None:
        """Mark a notification email as failed."""


class WeatherNotificationService:
    def __init__(
        self,
        *,
        repository: NotificationRepository,
        gmail_service: GmailNotificationService,
        email_formatter: WeatherEmailFormatter,
        gmail_settings: GmailSettings,
    ) -> None:
        self.repository = repository
        self.gmail_service = gmail_service
        self.email_formatter = email_formatter
        self.gmail_settings = gmail_settings

    @staticmethod
    def _safe_error_message(
        error: Exception,
    ) -> str:
        message = str(error).strip()

        if not message:
            message = error.__class__.__name__

        # Avoid storing very large Google API responses.
        return message[:500]

    def notify(
        self,
        alert: WeatherAlert,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
        recipient_email: str | None = None,
        email_authorized: bool = True,
    ) -> NotificationResult:
        if not isinstance(email_authorized, bool):
            raise TypeError(
                "email_authorized must be a boolean"
            )

        email_delivery_enabled = (
            self.gmail_settings.enabled
            and email_authorized
        )
        initial_email_status = (
            EmailStatus.PENDING
            if email_delivery_enabled
            else EmailStatus.SKIPPED
        )

        # The notification is stored before Gmail is called.
        created = self.repository.create_notification(
            alert,
            email_status=initial_email_status,
        )

        if not created:
            return NotificationResult(
                notification_id=alert.alert_id,
                created=False,
                email_status=EmailStatus.SKIPPED,
            )

        if not email_delivery_enabled:
            return NotificationResult(
                notification_id=alert.alert_id,
                created=True,
                email_status=EmailStatus.SKIPPED,
            )

        try:
            email_content = self.email_formatter.format(
                alert,
                device_name=device_name,
                location_name=location_name,
                timezone_name=timezone_name,
            )

            send_arguments = {
                "subject": email_content.subject,
                "body": email_content.body,
            }

            if recipient_email is not None:
                send_arguments["recipient_email"] = (
                    recipient_email
                )

            gmail_message_id = self.gmail_service.send_email(
                **send_arguments
            )
        except (
            GmailNotificationError,
            ValueError,
        ) as error:
            error_message = self._safe_error_message(
                error
            )

            try:
                self.repository.mark_email_failed(
                    device_id=alert.device_id,
                    notification_id=alert.alert_id,
                    error_message=error_message,
                )
            except Exception:
                logger.exception(
                    "Could not record failed Gmail "
                    "delivery for notification %s",
                    alert.alert_id,
                )

            logger.warning(
                "Gmail notification failed for %s: %s",
                alert.alert_id,
                error_message,
            )

            return NotificationResult(
                notification_id=alert.alert_id,
                created=True,
                email_status=EmailStatus.FAILED,
                error=error_message,
            )

        self.repository.mark_email_sent(
            device_id=alert.device_id,
            notification_id=alert.alert_id,
            gmail_message_id=gmail_message_id,
        )

        return NotificationResult(
            notification_id=alert.alert_id,
            created=True,
            email_status=EmailStatus.SENT,
            gmail_message_id=gmail_message_id,
        )
