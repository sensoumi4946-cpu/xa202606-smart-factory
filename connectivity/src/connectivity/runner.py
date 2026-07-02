# MQTT adapter entry point.
# Run as: python -m connectivity.runner
# This process subscribes to factory/+/sensors/#, normalises incoming
# payloads into UnifiedMessage, and forwards them to the backend.
import asyncio

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
