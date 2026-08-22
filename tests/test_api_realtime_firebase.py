import os
import unittest
import uuid

from backend.firebase import RealtimeFirebaseService


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
        cls.service = RealtimeFirebaseService.from_env()

        unique_suffix = uuid.uuid4().hex[:10]
        cls.device_id = (
            f"test_device_{unique_suffix}"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        # Remove only paths belonging to this unique test device.
        test_paths = [
            f"Input_Sensor/{cls.device_id}",
            f"Device_State/{cls.device_id}",
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

        state = self.service.set_rack_command(
            device_id=self.device_id,
            command="open",
        )

        saved_state = self.service.get_device_state(
            self.device_id
        )

        self.assertEqual(
            saved_state["rack_state"],
            state["rack_state"],
        )
        self.assertEqual(
            saved_state["mode"],
            "manual",
        )

        config = self.service.set_device_mode(
            self.device_id,
            "auto",
        )
        saved_config = self.service.get_device_state(
            self.device_id
        )
        self.assertEqual(saved_config["mode"], config["mode"])


if __name__ == "__main__":
    unittest.main()
