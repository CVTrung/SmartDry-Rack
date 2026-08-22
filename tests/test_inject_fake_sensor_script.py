import unittest

from unittest.mock import MagicMock

from scripts.inject_fake_sensor import (
    inject_fake_sensor,
    parse_arguments,
)


class InjectFakeSensorScriptTests(unittest.TestCase):
    def test_defaults_to_configured_device(self) -> None:
        service = MagicMock()
        service.set_sensor_data.return_value = {
            "device_id": "device_001"
        }

        result = inject_fake_sensor(
            parse_arguments([]),
            service,
            default_device_id="device_001",
        )

        self.assertEqual(result["device_id"], "device_001")
        service.set_sensor_data.assert_called_once_with(
            device_id="device_001",
            light_lux=650.0,
            humidity_percent=72.5,
            temperature_celsius=30.5,
            rain_detected=False,
        )

    def test_accepts_custom_rain_snapshot(self) -> None:
        service = MagicMock()
        service.set_sensor_data.return_value = {
            "device_id": "device_002"
        }
        arguments = parse_arguments([
            "--device-id",
            "device_002",
            "--light-lux",
            "120",
            "--humidity-percent",
            "90",
            "--temperature-celsius",
            "27",
            "--rain-detected",
        ])

        inject_fake_sensor(
            arguments,
            service,
            default_device_id="device_001",
        )

        service.set_sensor_data.assert_called_once_with(
            device_id="device_002",
            light_lux=120.0,
            humidity_percent=90.0,
            temperature_celsius=27.0,
            rain_detected=True,
        )


if __name__ == "__main__":
    unittest.main()
