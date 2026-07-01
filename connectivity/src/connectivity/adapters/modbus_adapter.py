from connectivity.adapters.base import BaseAdapter


class ModbusAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("Modbus adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("Modbus adapter not implemented in current phase")
