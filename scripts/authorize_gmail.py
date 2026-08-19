import argparse

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from backend.config import GmailSettings, get_settings
from backend.notifications.gmail_service import (
    GMAIL_SEND_SCOPES,
)


class GmailAuthorizationScriptError(RuntimeError):
    """Raised when Gmail authorization cannot complete."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Authorize SmartDry-Rack to send Gmail notifications."
        )
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Ignore the existing token and request "
            "authorization again."
        ),
    )

    return parser.parse_args()


def require_gmail_paths(
    settings: GmailSettings,
) -> tuple[Path, Path]:
    if not settings.enabled:
        raise GmailAuthorizationScriptError(
            "EMAIL_NOTIFICATIONS_ENABLED must be true"
        )

    credentials_path = settings.credentials_path
    token_path = settings.token_path

    if credentials_path is None:
        raise GmailAuthorizationScriptError(
            "GMAIL_CREDENTIALS_PATH is missing"
        )

    if token_path is None:
        raise GmailAuthorizationScriptError(
            "GMAIL_TOKEN_PATH is missing"
        )

    if not credentials_path.is_file():
        raise GmailAuthorizationScriptError(
            "Gmail OAuth credentials file was not found: "
            f"{credentials_path}"
        )

    return credentials_path, token_path


def load_existing_token(
    token_path: Path,
) -> Credentials | None:
    if (
        not token_path.is_file()
        or token_path.stat().st_size == 0
    ):
        return None

    try:
        return Credentials.from_authorized_user_file(
            str(token_path),
            GMAIL_SEND_SCOPES,
        )
    except (
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise GmailAuthorizationScriptError(
            "The existing Gmail token is invalid. "
            "Run this script with --force."
        ) from error


def request_authorization(
    credentials_path: Path,
) -> Credentials:
    try:
        flow = (
            InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                GMAIL_SEND_SCOPES,
            )
        )

        return flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )
    except Exception as error:
        raise GmailAuthorizationScriptError(
            "Gmail authorization did not complete"
        ) from error


def save_token(
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


def authorize_gmail(
    settings: GmailSettings,
    *,
    force: bool = False,
) -> Path:
    credentials_path, token_path = (
        require_gmail_paths(settings)
    )

    credentials = None

    if not force:
        credentials = load_existing_token(
            token_path
        )

    if (
        credentials
        and credentials.expired
        and credentials.refresh_token
    ):
        try:
            credentials.refresh(Request())
        except RefreshError:
            credentials = None

    if not credentials or not credentials.valid:
        credentials = request_authorization(
            credentials_path
        )

    if not credentials.valid:
        raise GmailAuthorizationScriptError(
            "Google returned invalid Gmail credentials"
        )

    save_token(
        credentials,
        token_path,
    )

    return token_path


def main() -> None:
    arguments = parse_arguments()
    settings = get_settings()

    token_path = authorize_gmail(
        settings.gmail,
        force=arguments.force,
    )

    print("Gmail authorization is valid.")
    print(f"Token saved to: {token_path}")


if __name__ == "__main__":
    main()