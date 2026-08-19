import unittest

from unittest.mock import MagicMock, patch

from backend.firebase.firebase_auth_service import (
    FirebaseAuthService,
)


class FirebaseAuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = object.__new__(FirebaseAuthService)
        self.service.app = MagicMock()
        self.service.firestore = MagicMock()
        self.service.firestore.create_account.return_value = {
            "device_id": "device_001",
            "display_name": "Laundry Rack",
            "enabled": True,
        }

    @patch(
        "backend.firebase.firebase_auth_service.auth.create_user"
    )
    def test_create_device_account_assigns_location(
        self,
        create_user: MagicMock,
    ) -> None:
        create_user.return_value.uid = "device_001"

        result = self.service.create_device_account(
            device_id="device_001",
            password="secret1",
            display_name="Laundry Rack",
            location_id="location_hcm",
            gmail="owner@gmail.com",
            gmail_authorized=True,
        )

        self.service.firestore.create_account.assert_called_once_with(
            device_id="device_001",
            display_name="Laundry Rack",
            location_id="location_hcm",
            gmail="owner@gmail.com",
            gmail_authorized=True,
            enabled=True,
        )
        self.assertEqual(result["uid"], "device_001")

    @patch(
        "backend.firebase.firebase_auth_service.auth.delete_user"
    )
    def test_delete_device_account_removes_auth_and_data(
        self,
        delete_user: MagicMock,
    ) -> None:
        events: list[str] = []
        self.service.firestore.delete_account.side_effect = (
            lambda device_id: events.append("firestore")
        )
        delete_user.side_effect = (
            lambda *args, **kwargs: events.append("auth")
        )

        self.service.delete_device_account("DEVICE_001")

        self.assertEqual(events, ["auth", "firestore"])
        self.service.firestore.delete_account.assert_called_once_with(
            "device_001"
        )
        delete_user.assert_called_once_with(
            "device_001",
            app=self.service.app,
        )


if __name__ == "__main__":
    unittest.main()
