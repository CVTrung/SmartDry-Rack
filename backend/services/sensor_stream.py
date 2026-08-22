import asyncio
import json
from typing import Any, AsyncIterator

from backend.firebase import RealtimeFirebaseService


class SensorEventStream:
    """Bridge a Firebase listener to a Server-Sent Events stream."""

    HEARTBEAT_SECONDS = 15

    def __init__(
        self,
        service: RealtimeFirebaseService,
        device_id: str,
    ) -> None:
        self.service = service
        self.device_id = device_id
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._event_queue: asyncio.Queue[tuple[str, Any]] = (
            asyncio.Queue()
        )
        self._listener: Any = None
        self._closed = False

    def start(self) -> None:
        """Start listening to the current device in Firebase."""

        if self._listener is not None:
            return

        self._event_loop = asyncio.get_running_loop()
        self._listener = self.service.listen_sensor_data(
            self.device_id,
            self._handle_firebase_event,
        )

    def _publish(self, event_name: str, data: Any) -> None:
        if self._closed or self._event_loop is None:
            return

        self._event_loop.call_soon_threadsafe(
            self._event_queue.put_nowait,
            (event_name, data),
        )

    def _handle_firebase_event(self, event: Any) -> None:
        try:
            # nhận được full trường từ node
            if ( 
                getattr(event, "path", "/") == "/"
                and (
                    isinstance(event.data, dict)
                    or event.data is None   
                )
            ):
                sensor_data = event.data
            else:
                # Nếu nhận ko full trường thôi thì gọi hàm này
                sensor_data = self.service.get_sensor_data(
                    self.device_id
                )

            self._publish("sensor", sensor_data)
        except Exception:
            self._publish(
                "error",
                {
                    "message": (
                        "Không thể đọc dữ liệu cảm biến từ Firebase."
                    )
                },
            )

    @staticmethod
    def _encode_event(event_name: str, data: Any) -> str:
        payload = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"event: {event_name}\ndata: {payload}\n\n"

    async def events(self) -> AsyncIterator[str]:
        """Yield SSE messages and close Firebase on disconnect."""
    
        try:
            yield "retry: 3000\n\n"

            while True:
                try:
                    event_name, data = await asyncio.wait_for(
                        self._event_queue.get(),
                        timeout=self.HEARTBEAT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                yield self._encode_event(event_name, data)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        if self._listener is not None:
            self._listener.close()
            self._listener = None