import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from firebase_admin import firestore

from backend.firebase.firestore_service import (
    FirestoreService,
)


class TestFirestoreValidation(unittest.TestCase):
    def test_normalizes_device_id(self) -> None:
        result = FirestoreService._validate_device_id(
            "  DEVICE_001  "
        )

        self.assertEqual(result, "device_001")

    def test_rejects_empty_device_id(self) -> None:
        with self.assertRaises(ValueError):
            FirestoreService._validate_device_id("   ")

    def test_rejects_invalid_device_id(self) -> None:
        with self.assertRaises(ValueError):
            FirestoreService._validate_device_id(
                "device/001"
            )

    def test_rejects_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            FirestoreService._validate_limit(0)

        with self.assertRaises(ValueError):
            FirestoreService._validate_limit(101)

    def test_rejects_datetime_without_timezone(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            FirestoreService._validate_datetime(
                datetime(2026, 8, 12, 10, 0),
                "recorded_at",
            )


class TestFirestoreServiceMock(unittest.TestCase):
    def setUp(self) -> None:
        # Skip __init__ to avoid real credentials/network.
        self.service = object.__new__(
            FirestoreService
        )

        self.service.app = MagicMock()
        self.service.database = MagicMock()

    def test_device_reference_uses_nested_path(
        self,
    ) -> None:
        devices_collection = MagicMock()
        device_reference = MagicMock()

        self.service.database.collection.return_value = (
            devices_collection
        )

        devices_collection.document.return_value = (
            device_reference
        )

        result = self.service._device_reference(
            "DEVICE_001"
        )

        self.service.database.collection.assert_called_once_with(
            "devices"
        )

        devices_collection.document.assert_called_once_with(
            "device_001"
        )

        self.assertIs(result, device_reference)

    @patch.object(
        FirestoreService,
        "get_account",
    )
    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_create_account_creates_account_and_device(
        self,
        mock_device_reference: MagicMock,
        mock_get_account: MagicMock,
    ) -> None:
        accounts_collection = MagicMock()
        account_reference = MagicMock()
        device_reference = MagicMock()
        batch = MagicMock()

        account_reference.get.return_value.exists = False
        device_reference.get.return_value.exists = False

        self.service.database.collection.return_value = (
            accounts_collection
        )

        accounts_collection.document.return_value = (
            account_reference
        )

        mock_device_reference.return_value = (
            device_reference
        )

        self.service.database.batch.return_value = batch

        expected_account = {
            "device_id": "device_001",
            "display_name": "Test Rack",
            "enabled": True,
        }

        mock_get_account.return_value = expected_account

        result = self.service.create_account(
            device_id="DEVICE_001",
            display_name="Test Rack",
            enabled=True,
        )

        self.assertEqual(result, expected_account)

        self.service.database.collection.assert_called_with(
            "accounts"
        )

        accounts_collection.document.assert_called_with(
            "device_001"
        )

        self.assertEqual(batch.create.call_count, 2)
        batch.commit.assert_called_once()

        first_payload = (
            batch.create.call_args_list[0].args[1]
        )

        second_payload = (
            batch.create.call_args_list[1].args[1]
        )

        self.assertEqual(
            first_payload["device_id"],
            "device_001",
        )

        self.assertEqual(
            second_payload["device_id"],
            "device_001",
        )

        self.assertIs(
            first_payload["created_at"],
            firestore.SERVER_TIMESTAMP,
        )

    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_create_sensor_history_uses_subcollection(
        self,
        mock_device_reference: MagicMock,
    ) -> None:
        device_reference = MagicMock()
        history_collection = MagicMock()
        history_reference = MagicMock()

        history_reference.id = "history_001"

        mock_device_reference.return_value = (
            device_reference
        )

        device_reference.collection.return_value = (
            history_collection
        )

        history_collection.document.return_value = (
            history_reference
        )

        result = self.service.save_sensor_record(
            device_id="device_001",
            light_lux=45000,
            humidity_percent=62.5,
            temperature_celsius=31.2,
            rain_detected=False,
            recorded_at=datetime(
                2026,
                8,
                12,
                8,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(result, "history_001")

        device_reference.collection.assert_called_once_with(
            "device_history"
        )

        history_reference.set.assert_called_once()

        payload = history_reference.set.call_args.args[0]

        self.assertEqual(
            payload["device_id"],
            "device_001",
        )

        self.assertEqual(
            payload["record_type"],
            "sensor",
        )

        self.assertEqual(
            payload["sensor"]["light_lux"],
            45000,
        )

        self.assertFalse(
            payload["sensor"]["rain_detected"]
        )

        self.assertIs(
            payload["received_at"],
            firestore.SERVER_TIMESTAMP,
        )

    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_rejects_invalid_sensor_values(
        self,
        mock_device_reference: MagicMock,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.save_sensor_record(
                device_id="device_001",
                light_lux=100,
                humidity_percent=101,
                temperature_celsius=30,
                rain_detected=False,
            )

        mock_device_reference.assert_not_called()

    @patch.object(
        FirestoreService,
        "get_command_history",
    )
    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_creates_website_command_history(
        self,
        mock_device_reference: MagicMock,
        mock_get_command: MagicMock,
    ) -> None:
        device_reference = MagicMock()
        command_collection = MagicMock()
        command_reference = MagicMock()

        mock_device_reference.return_value = (
            device_reference
        )

        device_reference.collection.return_value = (
            command_collection
        )

        command_collection.document.return_value = (
            command_reference
        )

        expected_command = {
            "command_id": "command_001",
            "device_id": "device_001",
            "status": "pending",
        }

        mock_get_command.return_value = expected_command

        result = self.service.create_command_history(
            command_id="command_001",
            device_id="device_001",
            action="retract",
            source="website",
            reason="manual_user_request",
            requested_by="device_001",
        )

        self.assertEqual(result, expected_command)

        device_reference.collection.assert_called_once_with(
            "command_history"
        )

        command_collection.document.assert_called_once_with(
            "command_001"
        )

        command_reference.create.assert_called_once()

        payload = command_reference.create.call_args.args[0]

        self.assertEqual(payload["action"], "retract")
        self.assertEqual(payload["source"], "website")
        self.assertEqual(payload["status"], "pending")

        self.assertEqual(
            payload["requested_by"],
            {
                "auth_uid": "device_001",
            },
        )

    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_creates_forecast_history(
        self,
        mock_device_reference: MagicMock,
    ) -> None:
        device_reference = MagicMock()
        forecast_collection = MagicMock()
        forecast_reference = MagicMock()

        forecast_reference.id = "forecast_001"

        mock_device_reference.return_value = (
            device_reference
        )

        device_reference.collection.return_value = (
            forecast_collection
        )

        forecast_collection.document.return_value = (
            forecast_reference
        )

        result = self.service.create_forecast_history(
            device_id="device_001",
            forecast_at=datetime(
                2026,
                8,
                12,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            weather={
                "condition": "Rain",
                "rain_probability_percent": 75,
            },
            location={
                "name": "Ho Chi Minh City",
            },
        )

        self.assertEqual(result, "forecast_001")

        device_reference.collection.assert_called_once_with(
            "forecast_history"
        )

        payload = forecast_reference.set.call_args.args[0]

        self.assertEqual(
            payload["device_id"],
            "device_001",
        )

        self.assertEqual(
            payload["weather"][
                "rain_probability_percent"
            ],
            75,
        )

        self.assertIs(
            payload["retrieved_at"],
            firestore.SERVER_TIMESTAMP,
        )

    @patch.object(
        FirestoreService,
        "_device_reference",
    )
    def test_get_device_history(
        self,
        mock_device_reference: MagicMock,
    ) -> None:
        device_reference = MagicMock()
        history_collection = MagicMock()
        ordered_query = MagicMock()
        limited_query = MagicMock()

        snapshot = MagicMock()
        snapshot.exists = True
        snapshot.id = "history_001"
        snapshot.to_dict.return_value = {
            "device_id": "device_001",
            "record_type": "sensor",
        }

        mock_device_reference.return_value = (
            device_reference
        )

        device_reference.collection.return_value = (
            history_collection
        )

        history_collection.order_by.return_value = (
            ordered_query
        )

        ordered_query.limit.return_value = limited_query
        limited_query.stream.return_value = [snapshot]

        result = self.service.get_device_history(
            device_id="device_001",
            limit=20,
        )

        self.assertEqual(
            result,
            [
                {
                    "document_id": "history_001",
                    "device_id": "device_001",
                    "record_type": "sensor",
                }
            ],
        )

        device_reference.collection.assert_called_once_with(
            "device_history"
        )

        ordered_query.limit.assert_called_once_with(20)


if __name__ == "__main__":
    unittest.main()