import base64

from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.config import GmailSettings
from backend.models import (
    AlertType,
    EmailContent,
    WeatherAlert,
)


GMAIL_SEND_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailNotificationError(RuntimeError):
    """Base error for Gmail notification failures."""


class GmailDisabledError(GmailNotificationError):
    """Raised when Gmail notifications are disabled."""


class GmailAuthorizationError(GmailNotificationError):
    """Raised when Gmail credentials cannot be loaded."""


class GmailSendError(GmailNotificationError):
    """Raised when Gmail cannot send a message."""


class GmailNotificationService:
    def __init__(
        self,
        settings: GmailSettings,
    ) -> None:
        self.settings = settings
        self._credentials: Credentials | None = None
        self._client: Any | None = None

    def _validate_configuration(
        self,
    ) -> tuple[str, str | None, Path]:
        if not self.settings.enabled:
            raise GmailDisabledError(
                "Gmail notifications are disabled"
            )

        sender_email = self.settings.sender_email
        recipient_email = self.settings.recipient_email
        token_path = self.settings.token_path

        if not sender_email:
            raise GmailAuthorizationError(
                "Gmail sender email is missing"
            )

        if token_path is None:
            raise GmailAuthorizationError(
                "Gmail token path is missing"
            )

        return (
            sender_email,
            recipient_email,
            token_path,
        )

    @staticmethod
    def _validate_email(
        email_address: str,
    ) -> str:
        email_address = email_address.strip()

        if (
            email_address.count("@") != 1
            or any(
                character.isspace()
                for character in email_address
            )
        ):
            raise ValueError(
                "Email address is invalid"
            )

        local_part, domain = email_address.rsplit(
            "@",
            1,
        )

        if (
            not local_part
            or not domain
            or "." not in domain
        ):
            raise ValueError(
                "Email address is invalid"
            )

        return email_address

    @staticmethod
    def _validate_subject(subject: str) -> str:
        subject = subject.strip()

        if not subject:
            raise ValueError(
                "Email subject must not be empty"
            )

        if "\r" in subject or "\n" in subject:
            raise ValueError(
                "Email subject must not contain newlines"
            )

        if len(subject) > 200:
            raise ValueError(
                "Email subject must not exceed 200 characters"
            )

        return subject

    @staticmethod
    def _validate_body(body: str) -> str:
        body = body.strip()

        if not body:
            raise ValueError(
                "Email body must not be empty"
            )

        return body

    def _save_credentials(
        self,
        credentials: Credentials,
        token_path: Path,
    ) -> None:
        token_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        token_path.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    def _load_credentials(
        self,
    ) -> Credentials:
        _, _, token_path = (
            self._validate_configuration()
        )

        if (
            not token_path.exists()
            or not token_path.is_file()
            or token_path.stat().st_size == 0
        ):
            raise GmailAuthorizationError(
                "Gmail token was not found or is empty. "
                "Run the Gmail authorization script first."
            )

        try:
            credentials = (
                Credentials.from_authorized_user_file(
                    str(token_path),
                    GMAIL_SEND_SCOPES,
                )
            )
        except (
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise GmailAuthorizationError(
                "Gmail token could not be loaded"
            ) from error

        if (
            credentials.expired
            and credentials.refresh_token
        ):
            try:
                credentials.refresh(Request())
            except RefreshError as error:
                raise GmailAuthorizationError(
                    "Gmail authorization expired or "
                    "was revoked"
                ) from error

            self._save_credentials(
                credentials,
                token_path,
            )

        if not credentials.valid:
            raise GmailAuthorizationError(
                "Gmail credentials are not valid. "
                "Authorize Gmail again."
            )

        return credentials

    def _get_credentials(self) -> Credentials:
        if (
            self._credentials is None
            or not self._credentials.valid
        ):
            self._credentials = (
                self._load_credentials()
            )

        return self._credentials

    def _get_client(self) -> Any:
        if self._client is None:
            credentials = self._get_credentials()

            try:
                self._client = build(
                    "gmail",
                    "v1",
                    credentials=credentials,
                    cache_discovery=False,
                )
            except Exception as error:
                raise GmailAuthorizationError(
                    "Gmail API client could not be created"
                ) from error

        return self._client

    def send_email(
        self,
        *,
        subject: str,
        body: str,
        recipient_email: str | None = None,
    ) -> str:
        sender_email, default_recipient, _ = (
            self._validate_configuration()
        )

        recipient = (
            recipient_email
            if recipient_email is not None
            else default_recipient
        )

        if not recipient:
            raise GmailAuthorizationError(
                "Gmail recipient email is missing"
            )

        sender_email = self._validate_email(
            sender_email
        )
        recipient = self._validate_email(recipient)
        subject = self._validate_subject(subject)
        body = self._validate_body(body)

        message = EmailMessage()
        message["From"] = sender_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode("utf-8")

        try:
            response = (
                self._get_client()
                .users()
                .messages()
                .send(
                    userId="me",
                    body={
                        "raw": encoded_message,
                    },
                )
                .execute(
                    num_retries=(
                        self.settings.max_retry_attempts
                        - 1
                    )
                )
            )
        except HttpError as error:
            raise GmailSendError(
                f"Gmail API rejected the message: {error}"
            ) from error
        except OSError as error:
            raise GmailSendError(
                "Could not connect to Gmail"
            ) from error

        message_id = response.get("id")

        if not message_id:
            raise GmailSendError(
                "Gmail did not return a message ID"
            )

        return str(message_id)


class WeatherEmailFormatter:
    """Build readable Gmail content for weather alerts."""

    @staticmethod
    def _timezone(timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(
                f"Unknown timezone: {timezone_name}"
            ) from error

    @classmethod
    def _datetime_text(
        cls,
        value: datetime,
        timezone_name: str,
    ) -> str:
        local_time = value.astimezone(
            cls._timezone(timezone_name)
        )
        return (
            local_time.strftime("%H:%M, %d %b %Y")
            + f" ({timezone_name})"
        )

    @classmethod
    def _short_time_text(
        cls,
        value: datetime,
        timezone_name: str,
    ) -> str:
        return value.astimezone(
            cls._timezone(timezone_name)
        ).strftime("%H:%M")

    @staticmethod
    def _location_text(
        location_id: str,
        location_name: str | None,
    ) -> str:
        if location_name and location_name.strip():
            return location_name.strip()

        readable_id = (
            location_id.strip()
            .lower()
            .removeprefix("location_")
            .replace("_", " ")
            .replace("-", " ")
        )
        return readable_id.title() or location_id

    @staticmethod
    def _duration_text(minutes: int) -> str:
        hours, remaining_minutes = divmod(minutes, 60)
        parts: list[str] = []

        if hours > 0:
            unit = "hour" if hours == 1 else "hours"
            parts.append(f"{hours} {unit}")

        if remaining_minutes > 0:
            unit = (
                "minute"
                if remaining_minutes == 1
                else "minutes"
            )
            parts.append(f"{remaining_minutes} {unit}")

        return " ".join(parts) if parts else "now"

    @staticmethod
    def _rain_amount_text(
        rain_amount_mm: float | None,
    ) -> str | None:
        if rain_amount_mm is None:
            return None
        return f"{rain_amount_mm:g} mm"

    def _format_current_rain(
        self,
        alert: WeatherAlert,
        *,
        device_name: str,
        location_name: str,
        timezone_name: str,
    ) -> EmailContent:
        if alert.observed_at is None:
            raise ValueError(
                "Current-rain alert is missing observed_at"
            )
        if alert.rain_started_at is None:
            raise ValueError(
                "Current-rain alert is missing rain_started_at"
            )

        detected_time = self._short_time_text(
            alert.observed_at,
            timezone_name,
        )
        subject = (
            "[SmartDry][CURRENT] "
            f"{device_name} - Rain at {detected_time}"
        )
        lines = [
            "SmartDry urgent rain alert",
            "",
            f"Rain has been detected at {location_name}.",
            "",
            f"Location: {location_name}",
            "Detected: "
            + self._datetime_text(
                alert.observed_at,
                timezone_name,
            ),
            "Rain began: "
            + self._datetime_text(
                alert.rain_started_at,
                timezone_name,
            ),
            f"Device: {device_name} ({alert.device_id})",
            "",
            "Action required:",
            "- Make sure the drying rack is retracted.",
            "- Protect any clothes still exposed to rain.",
        ]
        return EmailContent(
            subject=subject,
            body="\n".join(lines),
        )

    def _format_forecast_rain(
        self,
        alert: WeatherAlert,
        *,
        device_name: str,
        location_name: str,
        timezone_name: str,
    ) -> EmailContent:
        if alert.forecast_at is None:
            raise ValueError(
                "Forecast alert is missing forecast_at"
            )
        if alert.forecast_within_minutes is None:
            raise ValueError(
                "Forecast alert is missing "
                "forecast_within_minutes"
            )
        if alert.rain_probability_percent is None:
            raise ValueError(
                "Forecast alert is missing "
                "rain_probability_percent"
            )

        duration = self._duration_text(
            alert.forecast_within_minutes
        )
        forecast_time = self._short_time_text(
            alert.forecast_at,
            timezone_name,
        )
        subject = (
            "[SmartDry][FORECAST] "
            f"{device_name} - Rain at {forecast_time}"
        )
        lines = [
            "SmartDry rain forecast",
            "",
            f"Rain may reach {location_name} in {duration}.",
            "",
            f"Location: {location_name}",
            "Expected: "
            + self._datetime_text(
                alert.forecast_at,
                timezone_name,
            ),
            "Rain probability: "
            f"{alert.rain_probability_percent}%",
            f"Device: {device_name} ({alert.device_id})",
        ]

        rain_amount = self._rain_amount_text(
            alert.rain_amount_mm
        )
        if rain_amount is not None:
            lines.append(
                f"Expected rain amount: {rain_amount}"
            )

        lines.extend([
            "",
            "Recommended action:",
            "- Check the rack before the expected rain time.",
            "- Retract it if clothes are still outside.",
            "",
            "SmartDry will continue monitoring the weather.",
        ])
        return EmailContent(
            subject=subject,
            body="\n".join(lines),
        )

    def format(
        self,
        alert: WeatherAlert,
        *,
        device_name: str | None = None,
        location_name: str | None = None,
        timezone_name: str = "UTC",
    ) -> EmailContent:
        display_location = self._location_text(
            alert.location_id,
            location_name,
        )
        display_device = (
            device_name.strip()
            if device_name and device_name.strip()
            else alert.device_id
        )

        if alert.alert_type == AlertType.CURRENT_RAIN:
            return self._format_current_rain(
                alert,
                device_name=display_device,
                location_name=display_location,
                timezone_name=timezone_name,
            )
        if alert.alert_type == AlertType.NEAR_FORECAST_RAIN:
            return self._format_forecast_rain(
                alert,
                device_name=display_device,
                location_name=display_location,
                timezone_name=timezone_name,
            )

        raise ValueError(
            f"Unsupported alert type: {alert.alert_type}"
        )
