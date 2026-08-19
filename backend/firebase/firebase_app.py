from functools import lru_cache

import firebase_admin

from firebase_admin import credentials

from backend.config import (
    ConfigurationError,
    get_settings,
)


FIREBASE_APP_NAME = "smartdry-backend"


class FirebaseInitializationError(RuntimeError):
    """Raised when Firebase Admin cannot be initialized."""


@lru_cache(maxsize=1)
def get_firebase_app() -> firebase_admin.App:
    """Return the shared Firebase Admin application."""

    try:
        return firebase_admin.get_app(
            FIREBASE_APP_NAME
        )
    except ValueError:
        # The named Firebase app has not been created.
        pass

    try:
        firebase_settings = (
            get_settings().firebase
        )
    except ConfigurationError as error:
        raise FirebaseInitializationError(
            f"Invalid Firebase configuration: {error}"
        ) from error

    key_path = (
        firebase_settings
        .service_account_key_path
    )

    if not key_path.is_file():
        raise FirebaseInitializationError(
            "Firebase service account file "
            f"was not found: {key_path}"
        )

    try:
        credential = credentials.Certificate(
            str(key_path)
        )

        return firebase_admin.initialize_app(
            credential,
            {
                "databaseURL": (
                    firebase_settings.database_url
                ),
            },
            name=FIREBASE_APP_NAME,
        )
    except Exception as error:
        raise FirebaseInitializationError(
            "Could not initialize Firebase Admin: "
            f"{error}"
        ) from error