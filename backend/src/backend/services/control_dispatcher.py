# Publishes control commands onto MQTT so a device can act on them.

import asyncio
import json
import logging
from datetime import datetime, timezone

from backend import config

logger = logging.getLogger(__name__)

CONTROL_TIMEOUT = 5.0


def control_topic(device_id: str, subsystem: str = "actuator") -> str:
    return f"factory/{subsystem}/control/{device_id}"


def build_payload(command_id: str, device_id: str, action: str, params: dict) -> dict:
    return {
        "schema_version": "v1",
        "command_id": command_id,
        "device_id": device_id,
        "action": action,
        "params": params,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "ack_url": f"{config.PUBLIC_BACKEND_URL}/api/v1/control/{command_id}/ack",
    }


def _publish_blocking(topic: str, payload: dict) -> None:
    import paho.mqtt.publish as publish

    publish.single(
        topic,
        payload=json.dumps(payload),
        qos=1,
        hostname=config.MQTT_BROKER_HOST,
        port=config.MQTT_BROKER_PORT,
        keepalive=10,
    )


async def dispatch(
    command_id: str,
    device_id: str,
    action: str,
    params: dict,
    subsystem: str = "actuator",
) -> bool:
    """Push one command to the broker. Returns False if the broker is down.

    Never raises: a broker outage must not turn a button press into a 500.
    The command stays 'pending' in the database and the retry loop or the
    operator can deal with it.
    """
    topic = control_topic(device_id, subsystem)
    payload = build_payload(command_id, device_id, action, params)

    try:
        await asyncio.wait_for(
            asyncio.to_thread(_publish_blocking, topic, payload),
            timeout=CONTROL_TIMEOUT,
        )
    except Exception as exc:
        logger.warning(
            "control dispatch failed command_id=%s device=%s error=%s",
            command_id,
            device_id,
            exc,
        )
        return False

    logger.info(
        "control dispatched command_id=%s device=%s topic=%s action=%s",
        command_id,
        device_id,
        topic,
        action,
    )
    return True
