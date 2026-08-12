import unittest
from unittest.mock import MagicMock, patch

from backend.firebase.firebase_app import (
    FIREBASE_APP_NAME,
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


if __name__ == "__main__":
    unittest.main()