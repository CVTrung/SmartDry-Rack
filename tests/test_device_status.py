import unittest

from backend.services.device_status import DeviceHeartbeatTracker


class DeviceHeartbeatTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = DeviceHeartbeatTracker(
            timeout_seconds=15,
        )

    def test_first_snapshot_enters_checking_window(self) -> None:
        result = self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )

        self.assertFalse(result["online"])
        self.assertEqual(result["status"], "checking")
        self.assertEqual(result["stale_for_seconds"], 0)

    def test_unchanged_first_baseline_becomes_offline(self) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        result = self.tracker.observe(
            "device_001",
            100,
            monotonic_now=25,
            wall_now=1015,
        )

        self.assertFalse(result["online"])
        self.assertEqual(result["status"], "offline")
        self.assertEqual(result["stale_for_seconds"], 15)

    def test_changed_timestamp_marks_online(self) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        result = self.tracker.observe(
            "device_001",
            102,
            monotonic_now=12,
            wall_now=1002,
        )

        self.assertTrue(result["online"])
        self.assertEqual(result["status"], "online")
        self.assertEqual(result["last_change_observed_at"], 1002)
        self.assertEqual(result["stale_for_seconds"], 0)

    def test_unchanged_timestamp_is_offline_after_fifteen_seconds(
        self,
    ) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        self.tracker.observe(
            "device_001",
            102,
            monotonic_now=12,
            wall_now=1002,
        )
        result = self.tracker.observe(
            "device_001",
            102,
            monotonic_now=27,
            wall_now=1017,
        )

        self.assertFalse(result["online"])
        self.assertEqual(result["status"], "offline")
        self.assertEqual(result["stale_for_seconds"], 15)

    def test_large_stale_duration_is_bounded_above_threshold(
        self,
    ) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        self.tracker.observe(
            "device_001",
            102,
            monotonic_now=12,
            wall_now=1002,
        )
        result = self.tracker.observe(
            "device_001",
            102,
            monotonic_now=112,
            wall_now=1102,
        )

        self.assertFalse(result["online"])
        self.assertEqual(result["status"], "offline")
        self.assertEqual(result["stale_for_seconds"], 16)

    def test_uptime_reset_is_a_change(self) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        result = self.tracker.observe(
            "device_001",
            1,
            monotonic_now=11,
            wall_now=1001,
        )

        self.assertTrue(result["online"])
        self.assertEqual(result["sensor_timestamp"], 1)

    def test_missing_timestamp_is_offline(self) -> None:
        result = self.tracker.observe(
            "device_001",
            None,
            monotonic_now=10,
            wall_now=1000,
        )

        self.assertFalse(result["online"])
        self.assertIsNone(result["sensor_timestamp"])

    def test_missing_timestamp_forces_offline_after_online(
        self,
    ) -> None:
        self.tracker.observe(
            "device_001",
            100,
            monotonic_now=10,
            wall_now=1000,
        )
        self.tracker.observe(
            "device_001",
            102,
            monotonic_now=12,
            wall_now=1002,
        )
        result = self.tracker.observe(
            "device_001",
            None,
            monotonic_now=13,
            wall_now=1003,
        )

        self.assertFalse(result["online"])
        self.assertEqual(result["status"], "offline")


if __name__ == "__main__":
    unittest.main()
