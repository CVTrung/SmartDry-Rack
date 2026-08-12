import os
import unittest
import uuid

from backend.realtime_firebase_service import FirebaseService


RUN_INTEGRATION_TESTS = (
    os.getenv("RUN_FIREBASE_INTEGRATION_TESTS") == "1"
)


@unittest.skipUnless(
    RUN_INTEGRATION_TESTS,
    "Set RUN_FIREBASE_INTEGRATION_TESTS=1 "
    "to run real Firebase tests",
)
class TestFirebaseAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FirebaseService.from_env()

        unique_suffix = uuid.uuid4().hex[:10]
        cls.device_id = (
            f"test_device_{unique_suffix}"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        # Remove only paths belonging to this unique test device.
        test_paths = [
            f"Input_Sensor/{cls.device_id}",
            f"Input_Config/{cls.device_id}",
            f"Output_State/{cls.device_id}",
            f"Output_Forecast/{cls.device_id}",
        ]

        for path in test_paths:
            cls.service._reference(path).delete()

    def test_real_firebase_crud_flow(self) -> None:
        sensor = self.service.set_sensor_data(
            device_id=self.device_id,
            light_lux=45000,
            humidity_percent=62.5,
            temperature_celsius=31.2,
            rain_detected=False,
        )

        saved_sensor = self.service.get_sensor_data(
            self.device_id
        )

        self.assertIsNotNone(saved_sensor)
        self.assertEqual(
            saved_sensor["device_id"],
            self.device_id,
        )
        self.assertEqual(
            saved_sensor["light_lux"],
            sensor["light_lux"],
        )

        config = self.service.set_device_config(
            device_id=self.device_id,
            config={
                "mode": "auto",
            },
        )

        saved_config = self.service.get_device_config(
            self.device_id
        )

        self.assertEqual(saved_config, config)

        state = self.service.set_output_state(
            device_id=self.device_id,
            rack_state="extended",
            reason="integration_test",
        )

        saved_state = self.service.get_output_state(
            self.device_id
        )

        self.assertEqual(saved_state, state)

        notification_id = (
            self.service.create_forecast_notification(
                device_id=self.device_id,
                reason="rain_expected",
                forecast_within_minutes=45,
                rain_probability_percent=75,
            )
        )

        saved_notification = (
            self.service.get_forecast_notification(
                device_id=self.device_id,
                notification_id=notification_id,
            )
        )

        self.assertIsNotNone(saved_notification)
        self.assertEqual(
            saved_notification["device_id"],
            self.device_id,
        )
        self.assertEqual(
            saved_notification[
                "rain_probability_percent"
            ],
            75,
        )

        notifications = (
            self.service.get_device_forecasts(
                device_id=self.device_id,
                limit=10,
            )
        )

        self.assertIn(
            notification_id,
            notifications,
        )


if __name__ == "__main__":
    unittest.main()