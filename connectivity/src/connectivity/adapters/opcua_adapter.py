# OPC UA adapter skeleton — to be implemented in Phase 2+.
# Will use Eclipse Milo or asyncua to subscribe to OPC UA nodes.
from connectivity.adapters.base import BaseAdapter


class OPCUAAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("OPC UA adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("OPC UA adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("OPC UA adapter not implemented in current phase")
