import asyncio

from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

from connectivity.adapters.base import BaseAdapter


def make_message_from_node(
    node_id: str, value: float, device_id: str = "sensor_hcsr04_01"
) -> UnifiedMessage:
    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=Subsystem.AGV,
        protocol=Protocol.OPCUA,
        measurements=[
            Measurement(
                type=MeasurementType.DISTANCE,
                value=float(value),
                unit=Unit.CM,
            ),
        ],
        raw_payload={"node_id": node_id, "value": float(value)},
    )


class SubscriptionHandler:
    def __init__(
        self, queue: asyncio.Queue[UnifiedMessage], node_id: str, device_id: str
    ):
        self.queue = queue
        self.node_id = node_id
        self.device_id = device_id

    def datachange_notification(self, node, val, data):
        msg = make_message_from_node(self.node_id, float(val), self.device_id)
        self.queue.put_nowait(msg)


class OPCUAAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("OPC UA adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("OPC UA adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("OPC UA adapter not implemented in current phase")
