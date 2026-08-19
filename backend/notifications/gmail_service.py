import base64

from email.message import EmailMessage
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from backend.config import GmailSettings


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
