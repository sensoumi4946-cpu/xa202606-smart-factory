from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

class Subsystem(str, Enum):
    TEMP_HUMIDITY = "temp_humidity"
    LIGHTING = "lighting"
    GAS = "gas"
    AGV = "agv"
    COUNTING = "counting"


class Protocol(str, Enum):
    MQTT = "mqtt"
    MODBUS = "modbus"
    OPCUA = "opcua"
    REST = "rest"
    MOCK = "mock"


class MeasurementType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    OCCUPANCY = "occupancy"
    LIGHT_STATE = "light_state"
    SMOKE = "smoke"
    COMBUSTIBLE_GAS = "combustible_gas"
    CO = "co"
    DISTANCE = "distance"
    COUNT = "count"
    DEVICE_STATUS = "device_status"
    ERROR_CODE = "error_code"
    SENSOR_STATUS = "sensor_status"


class Unit(str, Enum):
    CELSIUS = "celsius"
    PERCENT = "percent"
    BOOLEAN = "boolean"
    PPM = "ppm"
    CM = "cm"
    COUNT = "count"
    STATUS = "status"


class Measurement(BaseModel):
    type: MeasurementType
    value: float = Field(allow_inf_nan=False)
    unit: Unit


class UnifiedMessage(BaseModel):
    schema_version: Literal["v1"]
    device_id: str = Field(..., min_length=1)
    subsystem: Subsystem
    protocol: Protocol
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    measurements: list[Measurement] = Field(..., min_length=1)
    raw_payload: Optional[dict] = None

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("device_id")
    @classmethod
    def nonblank_device(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("device_id must not be blank")
        return value