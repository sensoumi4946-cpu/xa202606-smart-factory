from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from connectivity.adapters.base import BaseAdapter

REGISTER_BASE = 0
REGISTER_COUNT = 3


def parse_registers(
    registers: list[int], device_id: str = "sensor_mq2_01"
) -> UnifiedMessage:
    if len(registers) < REGISTER_COUNT:
        raise ValueError("expected at least three holding registers")

    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=Subsystem.GAS,
        protocol=Protocol.MODBUS,
        measurements=[
            Measurement(
                type=MeasurementType.SMOKE,
                value=float(registers[0]),
                unit=Unit.PPM,
            ),
            Measurement(
                type=MeasurementType.CO,
                value=float(registers[1]),
                unit=Unit.PPM,
            ),
            Measurement(
                type=MeasurementType.COMBUSTIBLE_GAS,
                value=float(registers[2]),
                unit=Unit.PPM,
            ),
        ],
        raw_payload={
            "registers": list(registers[:REGISTER_COUNT]),
            "base_address": REGISTER_BASE,
        },
    )


class ModbusAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("Modbus adapter not implemented in current phase")
