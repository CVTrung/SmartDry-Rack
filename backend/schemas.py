from typing import Literal

from pydantic import BaseModel


class DeviceConfigRequest(BaseModel):
    mode: Literal["auto", "manual"]


class RackCommandRequest(BaseModel):
    command: Literal["open", "close"]
    client_request_id: str | None = None
