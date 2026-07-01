# REST adapter skeleton — to be implemented in Phase 2+.
# Will expose an HTTP endpoint that devices can POST sensor data to.
from connectivity.adapters.base import BaseAdapter


class RESTAdapter(BaseAdapter):
    async def start(self) -> None:
        raise NotImplementedError("REST adapter not implemented in current phase")

    async def stop(self) -> None:
        raise NotImplementedError("REST adapter not implemented in current phase")

    async def receive(self):
        raise NotImplementedError("REST adapter not implemented in current phase")
