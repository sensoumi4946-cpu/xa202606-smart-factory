# Core data contract for the XA-202606 Smart Factory platform.
#
# UnifiedMessage is the ONLY wire format between connectivity adapters
# and the backend API. Every sensor reading, regardless of origin
# protocol (MQTT, Modbus, OPC UA, REST), must be normalised into this
# structure before ingestion.
#
# Protocol versioning: schema_version is required (no default) so
# clients must explicitly declare which version they speak.
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Enumeration tables for the five sensor subsystems ──

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


class Unit(str, Enum):
    CELSIUS = "celsius"
    PERCENT = "percent"
    BOOLEAN = "boolean"
    PPM = "ppm"
    CM = "cm"
    COUNT = "count"


class Measurement(BaseModel):
    type: MeasurementType
    value: float
    unit: Unit


class UnifiedMessage(BaseModel):
    schema_version: Literal["v1"]
    device_id: str = Field(..., min_length=1)
    subsystem: Subsystem
    protocol: Protocol
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    measurements: list[Measurement] = Field(..., min_length=1)
    raw_payload: Optional[dict] = None
