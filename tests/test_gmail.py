import base64
import os
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
]


def required_environment_variable(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")

    return value


def load_gmail_credentials() -> Credentials:
    credentials_path = Path(
        required_environment_variable(
            "GMAIL_CREDENTIALS_PATH"
        )
    )
    token_path = Path(
        required_environment_variable(
            "GMAIL_TOKEN_PATH"
        )
    )

    credentials = None

    # Ignore the initial empty token file.
    if token_path.exists() and token_path.stat().st_size > 0:
        credentials = (
            Credentials.from_authorized_user_file(
                token_path,
                SCOPES,
            )
        )

    if not credentials or not credentials.valid:
        if (
            credentials
            and credentials.expired
            and credentials.refresh_token
        ):
            credentials.refresh(Request())
        else:
            flow = (
                InstalledAppFlow.from_client_secrets_file(
                    credentials_path,
                    SCOPES,
                )
            )
            credentials = flow.run_local_server(port=0)

        token_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        token_path.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    return credentials


def send_test_email() -> str:
    sender = required_environment_variable(
        "GMAIL_SENDER_EMAIL"
    )
    recipient = required_environment_variable(
        "GMAIL_RECIPIENT_EMAIL"
    )

    credentials = load_gmail_credentials()

    gmail = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient
    email["Subject"] = "SmartDry Gmail API test"
    email.set_content(
        "Gmail notifications are working correctly."
    )

    encoded_email = base64.urlsafe_b64encode(
        email.as_bytes()
    ).decode("utf-8")

    result = (
        gmail.users()
        .messages()
        .send(
            userId="me",
            body={"raw": encoded_email},
        )
        .execute()
    )

    return result["id"]


if __name__ == "__main__":
    load_dotenv()

    message_id = send_test_email()
    print(f"Email sent successfully: {message_id}")