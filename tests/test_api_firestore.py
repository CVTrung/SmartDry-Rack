import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from backend.firebase.firestore_service import (
    FirestoreService,
)


RUN_INTEGRATION_TESTS = (
    os.getenv("RUN_FIRESTORE_INTEGRATION_TESTS")
    == "1"
)


@unittest.skipUnless(
    RUN_INTEGRATION_TESTS,
    "Set RUN_FIRESTORE_INTEGRATION_TESTS=1 "
    "to run real Firestore tests",
)
class TestFirestoreAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FirestoreService()

        unique_suffix = uuid.uuid4().hex[:10]

        cls.device_id = (
            f"test_firestore_{unique_suffix}"
        )

        cls.command_id = (
            f"test_command_{unique_suffix}"
        )
        cls.location_id = (
            f"test_location_{unique_suffix}"
        )

        cls.service.create_account(
            device_id=cls.device_id,
            display_name="Firestore Test Rack",
            location_id=cls.location_id,
            gmail="firestore.test@gmail.com",
            gmail_authorized=True,
            enabled=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        # Delete only documents belonging to the unique
        # integration-test device.
        device_reference = (
            cls.service
            ._device_reference(cls.device_id)
        )

        subcollections = [
            cls.service.DEVICE_HISTORY,
            cls.service.COMMAND_HISTORY,
            cls.service.FORECAST_HISTORY,
        ]

        for subcollection_name in subcollections:
            snapshots = (
                device_reference
                .collection(subcollection_name)
                .stream()
            )

            for snapshot in snapshots:
                snapshot.reference.delete()

        device_reference.delete()

        (
            cls.service.database
            .collection(cls.service.ACCOUNTS)
            .document(cls.device_id)
            .delete()
        )

    def test_01_account_created(self) -> None:
        account = self.service.get_account(
            self.device_id
        )

        self.assertIsNotNone(account)

        self.assertEqual(
            account["device_id"],
            self.device_id,
        )

        self.assertEqual(
            account["display_name"],
            "Firestore Test Rack",
        )

        self.assertTrue(account["enabled"])

        self.assertTrue(
            self.service.account_is_enabled(
                self.device_id
            )
        )

    def test_02_sensor_history(self) -> None:
        history_id = self.service.save_sensor_record(
            device_id=self.device_id,
            light_lux=45000,
            humidity_percent=62.5,
            temperature_celsius=31.2,
            rain_detected=False,
            recorded_at=datetime.now(timezone.utc),
        )

        self.assertTrue(history_id)

        records = self.service.get_device_history(
            device_id=self.device_id,
            record_type="sensor",
            limit=10,
        )

        matching_records = [
            record
            for record in records
            if record["document_id"] == history_id
        ]

        self.assertEqual(len(matching_records), 1)

        sensor = matching_records[0]["sensor"]

        self.assertEqual(sensor["light_lux"], 45000)
        self.assertFalse(sensor["rain_detected"])

    def test_03_state_change_history(self) -> None:
        history_id = self.service.save_state_change(
            device_id=self.device_id,
            previous_state="extended",
            new_state="retracted",
            reason="integration_test",
            command_id=self.command_id,
            result="success",
            recorded_at=datetime.now(timezone.utc),
        )

        self.assertTrue(history_id)

        records = self.service.get_device_history(
            device_id=self.device_id,
            record_type="state_change",
            limit=10,
        )

        matching_records = [
            record
            for record in records
            if record["document_id"] == history_id
        ]

        self.assertEqual(len(matching_records), 1)

        state_change = (
            matching_records[0]["state_change"]
        )

        self.assertEqual(
            state_change["new_state"],
            "retracted",
        )

    def test_04_config_change_history(self) -> None:
        history_id = self.service.save_config_change(
            device_id=self.device_id,
            previous_config={
                "mode": "auto",
            },
            current_config={
                "mode": "manual",
            },
            changed_by=self.device_id,
            recorded_at=datetime.now(timezone.utc),
        )

        self.assertTrue(history_id)

    def test_05_command_lifecycle(self) -> None:
        command = (
            self.service.create_command_history(
                command_id=self.command_id,
                device_id=self.device_id,
                action="retract",
                source="website",
                reason="integration_test",
                requested_by=self.device_id,
            )
        )

        self.assertEqual(
            command["status"],
            "pending",
        )

        updated_command = (
            self.service.update_command_status(
                command_id=self.command_id,
                device_id=self.device_id,
                status="completed",
                previous_state="extended",
                final_state="retracted",
            )
        )

        self.assertEqual(
            updated_command["status"],
            "completed",
        )

        self.assertEqual(
            updated_command["result"]["final_state"],
            "retracted",
        )

        commands = self.service.get_device_commands(
            device_id=self.device_id,
            source="website",
            limit=10,
        )

        command_ids = {
            item["command_id"]
            for item in commands
        }

        self.assertIn(
            self.command_id,
            command_ids,
        )

    def test_06_physical_button_command(self) -> None:
        button_command_id = (
            f"{self.command_id}_button"
        )

        command = (
            self.service.create_command_history(
                command_id=button_command_id,
                device_id=self.device_id,
                action="extend",
                source="physical_button",
                reason="local_button_press",
                status="completed",
                result={
                    "previous_state": "retracted",
                    "final_state": "extended",
                    "error_code": None,
                },
            )
        )

        self.assertEqual(
            command["source"],
            "physical_button",
        )

        self.assertEqual(
            command["status"],
            "completed",
        )

    def test_07_forecast_history(self) -> None:
        now = datetime.now(timezone.utc)

        forecast_id = (
            self.service.create_forecast_history(
                device_id=self.device_id,
                forecast_at=now + timedelta(hours=3),
                expires_at=now + timedelta(days=1),
                location={
                    "name": "Ho Chi Minh City",
                    "latitude": 10.8231,
                    "longitude": 106.6297,
                },
                weather={
                    "condition": "Rain",
                    "temperature_celsius": 29.5,
                    "humidity_percent": 82,
                    "rain_probability_percent": 75,
                },
            )
        )

        self.assertTrue(forecast_id)

        forecasts = (
            self.service.get_device_forecasts(
                device_id=self.device_id,
                limit=10,
            )
        )

        forecast_ids = {
            forecast["document_id"]
            for forecast in forecasts
        }

        self.assertIn(
            forecast_id,
            forecast_ids,
        )


if __name__ == "__main__":
    unittest.main()
