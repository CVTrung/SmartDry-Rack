import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.firebase import RealtimeFirebaseService

class TestRealtimeFirebaseServiceMock(unittest.TestCase):
    def setUp(self) -> None:
        # Skip the real constructor so no credential file or
        # network connection is required.
        self.service = object.__new__(RealtimeFirebaseService)
        self.service.app = MagicMock()

        self.reference = MagicMock()
        self.service._reference = MagicMock(
            return_value=self.reference
        )

    @patch.object(
        RealtimeFirebaseService,
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
        RealtimeFirebaseService,
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
        RealtimeFirebaseService,
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
        RealtimeFirebaseService,
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

        ordered_query = (
            self.reference.order_by_key.return_value
        )

        limited_query = (
            ordered_query.limit_to_last.return_value
        )

        limited_query.get.return_value = expected

        result = self.service.get_device_forecasts(
            device_id="device_001",
            limit=5,
        )

        self.service._reference.assert_called_once_with(
            "Output_Forecast/device_001"
        )

        self.reference.order_by_key.assert_called_once_with()

        ordered_query.limit_to_last.assert_called_once_with(
            5
        )

        limited_query.get.assert_called_once_with()

        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()