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

    def test_get_sensor_timestamp_uses_canonical_node(self) -> None:
        self.reference.get.return_value = 42

        result = self.service.get_sensor_timestamp("device_001")

        self.service._reference.assert_called_once_with(
            "Input_Sensor/device_001/timestamp"
        )
        self.assertEqual(result, 42)

    def test_get_sensor_timestamp_supports_legacy_casing(
        self,
    ) -> None:
        canonical_reference = MagicMock()
        legacy_reference = MagicMock()
        canonical_reference.get.return_value = None
        legacy_reference.get.return_value = 44
        self.service._reference.side_effect = [
            canonical_reference,
            legacy_reference,
        ]

        result = self.service.get_sensor_timestamp("device_001")

        self.assertEqual(
            self.service._reference.call_args_list,
            [
                unittest.mock.call(
                    "Input_Sensor/device_001/timestamp"
                ),
                unittest.mock.call(
                    "Input_sensor/device_001/timestamp"
                ),
            ],
        )
        self.assertEqual(result, 44)

    def test_get_device_state(self) -> None:
        expected = {
            "device_id": "device_001",
            "mode": "auto",
            "rack_state": "retracted",
        }
        self.reference.get.return_value = expected

        result = self.service.get_device_state("device_001")

        self.service._reference.assert_called_once_with(
            "Device_State/device_001"
        )
        self.assertEqual(result, expected)

    @patch.object(
        RealtimeFirebaseService,
        "_timestamp",
        return_value=1786512040,
    )
    def test_set_device_mode(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_device_mode(
            "device_001",
            "manual",
        )

        self.service._reference.assert_called_once_with(
            "Device_State/device_001"
        )
        self.reference.update.assert_called_once_with({
            "device_id": "device_001",
            "mode": "manual",
            "updated_at": 1786512040,
        })
        self.assertEqual(result["mode"], "manual")

    @patch.object(
        RealtimeFirebaseService,
        "_timestamp",
        return_value=1786512050,
    )
    def test_open_rack_command_atomically_sets_manual_extended(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_rack_command(
            device_id="device_001",
            command="open",
        )

        self.service._reference.assert_called_once_with("/")
        self.reference.update.assert_called_once_with({
            "Device_State/device_001/device_id": "device_001",
            "Device_State/device_001/mode": "manual",
            "Device_State/device_001/rack_state": "extended",
            "Device_State/device_001/updated_at": 1786512050,
        })
        self.assertEqual(result["rack_state"], "extended")
        self.assertEqual(result["mode"], "manual")

    @patch.object(
        RealtimeFirebaseService,
        "_timestamp",
        return_value=1786512060,
    )
    def test_close_rack_command_atomically_sets_manual_retracted(
        self,
        mock_timestamp: MagicMock,
    ) -> None:
        result = self.service.set_rack_command(
            device_id="device_001",
            command="close",
        )

        self.service._reference.assert_called_once_with("/")
        self.reference.update.assert_called_once_with({
            "Device_State/device_001/device_id": "device_001",
            "Device_State/device_001/mode": "manual",
            "Device_State/device_001/rack_state": "retracted",
            "Device_State/device_001/updated_at": 1786512060,
        })
        self.assertEqual(result["rack_state"], "retracted")

if __name__ == "__main__":
    unittest.main()
