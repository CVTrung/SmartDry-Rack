import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.services.sensor_stream import SensorEventStream


class TestSensorEventStream(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = MagicMock()
        self.listener = MagicMock()
        self.service.listen_sensor_data.return_value = self.listener
        self.stream = SensorEventStream(
            service=self.service,
            device_id="device_001",
        )
        self.stream.start()
        self.callback = self.service.listen_sensor_data.call_args.args[1]
        self.events = self.stream.events()

    async def asyncTearDown(self) -> None:
        await self.events.aclose()

    async def test_streams_complete_sensor_payload(self) -> None:
        payload = {
            "device_id": "device_001",
            "timestamp": 1786512000,
            "light_lux": 45000,
            "humidity_percent": 62.5,
            "temperature_celsius": 31.2,
            "rain_detected": False,
        }
        self.callback(SimpleNamespace(path="/", data=payload))

        self.assertEqual(
            await anext(self.events),
            "retry: 3000\n\n",
        )

        encoded_event = await anext(self.events)
        event_payload = json.loads(
            encoded_event.split("data: ", 1)[1]
        )

        self.assertTrue(encoded_event.startswith("event: sensor\n"))
        self.assertEqual(event_payload, payload)

    async def test_child_update_reads_complete_node(self) -> None:
        complete_payload = {
            "device_id": "device_001",
            "humidity_percent": 64,
        }
        self.service.get_sensor_data.return_value = complete_payload
        self.callback(
            SimpleNamespace(
                path="/humidity_percent",
                data=64,
            )
        )

        await anext(self.events)
        encoded_event = await anext(self.events)

        self.service.get_sensor_data.assert_called_once_with(
            "device_001"
        )
        self.assertIn('"humidity_percent":64', encoded_event)

    async def test_closing_stream_closes_firebase_listener(self) -> None:
        await anext(self.events)
        await self.events.aclose()

        self.listener.close.assert_called_once_with()


class TestSensorStreamEndpoint(unittest.IsolatedAsyncioTestCase):
    @patch("backend.routers.sensors.SensorEventStream")
    async def test_uses_authenticated_device_id(
        self,
        mock_stream_class: MagicMock,
    ) -> None:
        from backend import dependencies
        from backend.routers.sensors import stream_sensor_data

        async def empty_events():
            if False:
                yield ""

        mock_stream = mock_stream_class.return_value
        mock_stream.events.return_value = empty_events()

        response = await stream_sensor_data(
            {
                "device_id": "device_001",
                "display_name": "Device 001",
                "enabled": True,
            }
        )

        mock_stream_class.assert_called_once_with(
            service=dependencies.realtime_firebase_service,
            device_id="device_001",
        )
        mock_stream.start.assert_called_once_with()
        self.assertEqual(response.media_type, "text/event-stream")
        await response.body_iterator.aclose()


if __name__ == "__main__":
    unittest.main()
