# Modbus adapter skeleton — to be implemented in Phase 2+.
# Will poll Modbus RTU/TCP registers and convert to UnifiedMessage.
from connectivity.adapters.base import BaseAdapter


class ModbusAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("Modbus adapter not implemented in current phase")
