import asyncio
import unittest

from unittest.mock import MagicMock, patch

from backend.config import SENSOR_HISTORY_INTERVAL_SECONDS
from backend.services.sensor_history import SensorHistoryRunner


class SensorHistoryRunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.realtime = MagicMock()
        self.repository = MagicMock()
        self.runner = SensorHistoryRunner(
            realtime=self.realtime,
            repository=self.repository,
        )

    def test_snapshots_enabled_devices_dynamically(self) -> None:
        self.repository.get_enabled_accounts.return_value = [
            {"device_id": "device_002"},
            {"document_id": "DEVICE_001"},
            {"device_id": "device_002"},
            {"enabled": True},
        ]
        sensor_one = {"device_id": "device_001"}
        sensor_two = {"device_id": "device_002"}
        self.realtime.get_sensor_data.side_effect = [
            sensor_one,
            sensor_two,
        ]

        saved_count = self.runner.snapshot_enabled_devices()

        self.assertEqual(saved_count, 2)
        self.assertEqual(
            self.realtime.get_sensor_data.call_args_list,
            [
                unittest.mock.call("device_001"),
                unittest.mock.call("device_002"),
            ],
        )
        self.assertEqual(
            self.repository.save_sensor_snapshot.call_args_list,
            [
                unittest.mock.call("device_001", sensor_one),
                unittest.mock.call("device_002", sensor_two),
            ],
        )

    def test_missing_snapshot_is_skipped(self) -> None:
        self.repository.get_enabled_accounts.return_value = [
            {"device_id": "device_001"},
        ]
        self.realtime.get_sensor_data.return_value = None

        saved_count = self.runner.snapshot_enabled_devices()

        self.assertEqual(saved_count, 0)
        self.repository.save_sensor_snapshot.assert_not_called()

    def test_one_device_failure_does_not_stop_other_devices(self) -> None:
        self.repository.get_enabled_accounts.return_value = [
            {"device_id": "device_001"},
            {"device_id": "device_002"},
        ]
        sensor_two = {"device_id": "device_002"}
        self.realtime.get_sensor_data.side_effect = [
            RuntimeError("RTDB unavailable"),
            sensor_two,
        ]

        with self.assertLogs(
            "backend.services.sensor_history",
            level="ERROR",
        ):
            saved_count = self.runner.snapshot_enabled_devices()

        self.assertEqual(saved_count, 1)
        self.repository.save_sensor_snapshot.assert_called_once_with(
            "device_002",
            sensor_two,
        )

    async def test_start_is_idempotent_and_stop_cancels_task(self) -> None:
        blocker = asyncio.Event()

        async def wait_forever() -> None:
            await blocker.wait()

        with patch.object(
            self.runner,
            "_repeat",
            new=wait_forever,
        ):

            await self.runner.start()
            first_task = self.runner._task
            await self.runner.start()
            await asyncio.sleep(0)

            self.assertIs(self.runner._task, first_task)
            await self.runner.stop()
            self.assertFalse(self.runner.running)

    async def test_repeat_uses_five_minute_interval(self) -> None:
        with (
            patch.object(
                self.runner,
                "_run_safely",
                side_effect=[None, asyncio.CancelledError],
            ) as run_safely,
            patch(
                "backend.services.sensor_history.asyncio.sleep",
                return_value=None,
            ) as sleep,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.runner._repeat()

        run_safely.assert_awaited()
        sleep.assert_awaited_once_with(
            SENSOR_HISTORY_INTERVAL_SECONDS
        )

    def test_rejects_invalid_interval(self) -> None:
        with self.assertRaises(ValueError):
            SensorHistoryRunner(
                realtime=self.realtime,
                repository=self.repository,
                interval_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
