import asyncio
import os

from connectivity.adapters.mqtt_adapter import MQTTAdapter


async def main():
    adapter = MQTTAdapter()
    try:
        await adapter.start()
    except KeyboardInterrupt:
        pass
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
