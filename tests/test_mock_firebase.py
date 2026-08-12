import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.firebase_service import FirebaseService


class TestFirebaseInitialization(unittest.TestCase):
    def test_reuses_existing_firebase_app(self) -> None:
        service = object.__new__(FirebaseService)
        existing_app = MagicMock()

        with patch(
            "backend.firebase_service.firebase_admin.get_app",
            return_value=existing_app,
        ) as mock_get_app:
            result = service._initialize_app()

        self.assertIs(result, existing_app)
        mock_get_app.assert_called_once_with(
            FirebaseService.APP_NAME
        )

    def test_initializes_new_firebase_app(self) -> None:
        service = object.__new__(FirebaseService)
        service.service_account_path = Path(
            "fake-service-account.json"
        )
        service.database_url = (
            "https://example-default-rtdb.firebaseio.com"
        )

        credential = MagicMock()
        initialized_app = MagicMock()

        with (
            patch(
                "backend.firebase_service.firebase_admin.get_app",
                side_effect=ValueError,
            ),
            patch(
                "backend.firebase_service.credentials.Certificate",
                return_value=credential,
            ) as mock_certificate,
            patch(
                "backend.firebase_service.firebase_admin.initialize_app",
                return_value=initialized_app,
            ) as mock_initialize,
        ):
            result = service._initialize_app()

        self.assertIs(result, initialized_app)

        mock_certificate.assert_called_once_with(
            str(service.service_account_path)
        )

        mock_initialize.assert_called_once_with(
            credential,
            {
                "databaseURL": service.database_url,
            },
            name=FirebaseService.APP_NAME,
        )


class TestFirebaseServiceMock(unittest.TestCase):
    def setUp(self) -> None:
        # Skip the real constructor so no credential file or
        # network connection is required.
        self.service = object.__new__(FirebaseService)
        self.service.app = MagicMock()

        self.reference = MagicMock()
        self.service._reference = MagicMock(
            return_value=self.reference
        )

    @patch.object(
        FirebaseService,
        "_timestamp",
        return_value=1786512000,
    )
    def test_set_sensor_data(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_sensor_data(
            device_id="device_001",
            light_lux=45000,
            humidity_percent=62.5,
            temperature_celsius=31.2,
            rain_detected=False,
        )

        expected = {
            "device_id": "device_001",
            "timestamp": 1786512000,
            "light_lux": 45000,
            "humidity_percent": 62.5,
            "temperature_celsius": 31.2,
            "rain_detected": False,
        }

        self.service._reference.assert_called_once_with(
            "Input_Sensor/device_001"
        )
        self.reference.set.assert_called_once_with(expected)
        self.assertEqual(result, expected)
        mock_timestamp.assert_called_once()

    def test_set_sensor_rejects_invalid_humidity(self) -> None:
        with self.assertRaises(ValueError):
            self.service.set_sensor_data(
                device_id="device_001",
                light_lux=45000,
                humidity_percent=101,
                temperature_celsius=31.2,
                rain_detected=False,
            )

        self.reference.set.assert_not_called()

    def test_set_sensor_rejects_invalid_temperature(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.set_sensor_data(
                device_id="device_001",
                light_lux=45000,
                humidity_percent=62.5,
                temperature_celsius=100,
                rain_detected=False,
            )

        self.reference.set.assert_not_called()

    def test_set_sensor_rejects_invalid_device_id(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.service.set_sensor_data(
                device_id="device/001",
                light_lux=45000,
                humidity_percent=62.5,
                temperature_celsius=31.2,
                rain_detected=False,
            )

        self.reference.set.assert_not_called()

    @patch.object(
        FirebaseService,
        "_timestamp",
        return_value=1786512010,
    )
    def test_set_device_config(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_device_config(
            device_id="device_001",
            config={
                "mode": "auto",
            },
        )

        expected = {
            "device_id": "device_001",
            "updated_at": 1786512010,
            "mode": "auto",
        }

        self.service._reference.assert_called_once_with(
            "Input_Config/device_001"
        )
        self.reference.set.assert_called_once_with(expected)
        self.assertEqual(result, expected)

    @patch.object(
        FirebaseService,
        "_timestamp",
        return_value=1786512020,
    )
    def test_set_output_state(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_output_state(
            device_id="device_001",
            rack_state="extended",
            reason="weather_clear",
        )

        expected = {
            "device_id": "device_001",
            "updated_at": 1786512020,
            "rack_state": "extended",
            "reason": "weather_clear",
        }

        self.service._reference.assert_called_once_with(
            "Output_State/device_001"
        )
        self.reference.set.assert_called_once_with(expected)
        self.assertEqual(result, expected)

    @patch.object(
        FirebaseService,
        "_timestamp",
        return_value=1786512030,
    )
    def test_create_forecast_notification(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        pushed_reference = MagicMock()
        pushed_reference.key = "notification_001"
        self.reference.push.return_value = pushed_reference

        result = self.service.create_forecast_notification(
            device_id="device_001",
            reason="rain_expected",
            forecast_within_minutes=45,
            rain_probability_percent=75,
        )

        expected = {
            "device_id": "device_001",
            "notified_at": 1786512030,
            "reason": "rain_expected",
            "forecast_within_minutes": 45,
            "rain_probability_percent": 75,
        }

        self.service._reference.assert_called_once_with(
            "Output_Forecast/device_001"
        )
        self.reference.push.assert_called_once_with(expected)
        self.assertEqual(result, "notification_001")

    def test_get_sensor_data(self) -> None:
        expected = {
            "device_id": "device_001",
            "light_lux": 45000,
        }
        self.reference.get.return_value = expected

        result = self.service.get_sensor_data(
            "device_001"
        )

        self.service._reference.assert_called_once_with(
            "Input_Sensor/device_001"
        )
        self.assertEqual(result, expected)

    def test_get_missing_sensor_returns_none(self) -> None:
        self.reference.get.return_value = None

        result = self.service.get_sensor_data(
            "device_001"
        )

        self.assertIsNone(result)

    def test_get_device_forecasts(self) -> None:
        expected = {
            "notification_001": {
                "device_id": "device_001",
                "reason": "rain_expected",
            }
        }

        query = self.reference.limit_to_last.return_value
        query.get.return_value = expected

        result = self.service.get_device_forecasts(
            device_id="device_001",
            limit=5,
        )

        self.service._reference.assert_called_once_with(
            "Output_Forecast/device_001"
        )
        self.reference.limit_to_last.assert_called_once_with(5)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()