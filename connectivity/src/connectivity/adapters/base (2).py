from abc import ABC, abstractmethod

from smart_factory_contracts.messages import UnifiedMessage


class BaseAdapter(ABC):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def receive(self) -> UnifiedMessage:
        raise NotImplementedError
