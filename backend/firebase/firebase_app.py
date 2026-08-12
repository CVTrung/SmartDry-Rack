import os
from functools import lru_cache
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
FIREBASE_APP_NAME = "smartdry-backend"

load_dotenv(ENV_FILE)


class FirebaseInitializationError(RuntimeError):
    """Raised when Firebase Admin cannot be initialized."""


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    """Return the shared Firebase Admin application."""

    try:
        return firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        pass

    database_url = os.getenv(
        "FIREBASE_DATABASE_URL",
        "",
    ).strip()

    service_account_path = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_KEY_PATH",
        "",
    ).strip()

    if not database_url:
        raise FirebaseInitializationError(
            "FIREBASE_DATABASE_URL is missing from .env"
        )

    if not service_account_path:
        raise FirebaseInitializationError(
            "FIREBASE_SERVICE_ACCOUNT_KEY_PATH "
            "is missing from .env"
        )

    key_path = Path(service_account_path)

    if not key_path.is_absolute():
        key_path = PROJECT_ROOT / key_path

    key_path = key_path.resolve()

    if not key_path.is_file():
        raise FirebaseInitializationError(
            "Firebase service account file was not found: "
            f"{key_path}"
        )

    try:
        credential = credentials.Certificate(str(key_path))

        return firebase_admin.initialize_app(
            credential,
            {
                "databaseURL": database_url.rstrip("/"),
            },
            name=FIREBASE_APP_NAME,
        )
    except Exception as error:
        raise FirebaseInitializationError(
            f"Could not initialize Firebase Admin: {error}"
        ) from error