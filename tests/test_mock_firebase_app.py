import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.config import (
    ConfigurationError,
    FirebaseSettings,
)

from backend.firebase.firebase_app import (
    FIREBASE_APP_NAME,
    FirebaseInitializationError,
    get_firebase_app,
)


class TestFirebaseApp(unittest.TestCase):
    def setUp(self) -> None:
        get_firebase_app.cache_clear()

    def tearDown(self) -> None:
        get_firebase_app.cache_clear()

    def test_reuses_existing_app(self) -> None:
        existing_app = MagicMock()

        with patch(
            "backend.firebase.firebase_app"
            ".firebase_admin.get_app",
            return_value=existing_app,
        ) as mock_get_app:
            result = get_firebase_app()

        self.assertIs(result, existing_app)

        mock_get_app.assert_called_once_with(
            FIREBASE_APP_NAME
        )

    def test_initializes_app_from_settings(
        self,
    ) -> None:
        initialized_app = MagicMock()
        credential = MagicMock()

        with TemporaryDirectory() as directory:
            key_path = (
                Path(directory)
                / "service-account.json"
            )
            key_path.write_text(
                "{}",
                encoding="utf-8",
            )

            firebase_settings = FirebaseSettings(
                database_url=(
                    "https://example.firebaseio.com"
                ),
                service_account_key_path=key_path,
            )

            settings = MagicMock()
            settings.firebase = firebase_settings

            with (
                patch(
                    (
                        "backend.firebase.firebase_app."
                        "firebase_admin.get_app"
                    ),
                    side_effect=ValueError(
                        "App does not exist"
                    ),
                ),
                patch(
                    (
                        "backend.firebase.firebase_app."
                        "get_settings"
                    ),
                    return_value=settings,
                ),
                patch(
                    (
                        "backend.firebase.firebase_app."
                        "credentials.Certificate"
                    ),
                    return_value=credential,
                ) as certificate,
                patch(
                    (
                        "backend.firebase.firebase_app."
                        "firebase_admin.initialize_app"
                    ),
                    return_value=initialized_app,
                ) as initialize_app,
            ):
                result = get_firebase_app()

        self.assertIs(
            result,
            initialized_app,
        )

        certificate.assert_called_once_with(
            str(key_path)
        )

        initialize_app.assert_called_once_with(
            credential,
            {
                "databaseURL": (
                    "https://example.firebaseio.com"
                ),
            },
            name=FIREBASE_APP_NAME,
        )


    def test_rejects_missing_service_account_file(
        self,
    ) -> None:
        missing_path = Path(
            "missing-service-account.json"
        )

        firebase_settings = FirebaseSettings(
            database_url=(
                "https://example.firebaseio.com"
            ),
            service_account_key_path=missing_path,
        )

        settings = MagicMock()
        settings.firebase = firebase_settings

        with (
            patch(
                (
                    "backend.firebase.firebase_app."
                    "firebase_admin.get_app"
                ),
                side_effect=ValueError(
                    "App does not exist"
                ),
            ),
            patch(
                (
                    "backend.firebase.firebase_app."
                    "get_settings"
                ),
                return_value=settings,
            ),
        ):
            with self.assertRaises(
                FirebaseInitializationError
            ):
                get_firebase_app()


    def test_converts_configuration_error(
        self,
    ) -> None:
        with (
            patch(
                (
                    "backend.firebase.firebase_app."
                    "firebase_admin.get_app"
                ),
                side_effect=ValueError(
                    "App does not exist"
                ),
            ),
            patch(
                (
                    "backend.firebase.firebase_app."
                    "get_settings"
                ),
                side_effect=ConfigurationError(
                    "FIREBASE_DATABASE_URL is missing"
                ),
            ),
        ):
            with self.assertRaisesRegex(
                FirebaseInitializationError,
                "Invalid Firebase configuration",
            ):
                get_firebase_app()


if __name__ == "__main__":
    unittest.main()