# Mock sensor data generator — development tool for testing the data
# pipeline without real hardware.
#
# Publishes realistic randomised readings for all five subsystems to
# MQTT topics matching the factory/{subsystem}/sensors/{device}/{type}
# convention. Run as: python -m analytics.mock.generator --count 5
#
# Data ranges match physical sensor specifications:
#   temperature 15-40°C, humidity 20-90%, CO 0-50ppm, distance 10-400cm
import argparse
import json
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from smart_factory_contracts.messages import (
    Measurement,
    MeasurementType,
    Protocol,
    Subsystem,
    UnifiedMessage,
    Unit,
)

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
DEFAULT_INTERVAL = float(os.getenv("MOCK_INTERVAL", "2.0"))


def generate_message(device_id: str, subsystem: Subsystem) -> UnifiedMessage:
    if subsystem == Subsystem.TEMP_HUMIDITY:
        measurements = [
            Measurement(
                type=MeasurementType.TEMPERATURE,
                value=round(random.uniform(15.0, 40.0), 1),
                unit=Unit.CELSIUS,
            ),
            Measurement(
                type=MeasurementType.HUMIDITY,
                value=round(random.uniform(20.0, 90.0), 1),
                unit=Unit.PERCENT,
            ),
        ]
    elif subsystem == Subsystem.LIGHTING:
        occ = random.choice([0.0, 1.0])
        light = 1.0 if occ > 0 else random.choice([0.0, 1.0])
        measurements = [
            Measurement(type=MeasurementType.OCCUPANCY, value=occ, unit=Unit.BOOLEAN),
            Measurement(
                type=MeasurementType.LIGHT_STATE, value=light, unit=Unit.BOOLEAN
            ),
        ]
    elif subsystem == Subsystem.GAS:
        smoke = round(random.uniform(0, 10), 1)
        co = round(random.uniform(0, 50), 1)
        cgas = round(random.uniform(0, 5), 1)
        measurements = [
            Measurement(type=MeasurementType.SMOKE, value=smoke, unit=Unit.PPM),
            Measurement(type=MeasurementType.CO, value=co, unit=Unit.PPM),
            Measurement(
                type=MeasurementType.COMBUSTIBLE_GAS, value=cgas, unit=Unit.PPM
            ),
        ]
    elif subsystem == Subsystem.AGV:
        distance = round(random.uniform(10.0, 400.0), 1)
        measurements = [
            Measurement(type=MeasurementType.DISTANCE, value=distance, unit=Unit.CM),
        ]
    elif subsystem == Subsystem.COUNTING:
        count = round(random.uniform(0, 200), 0)
        measurements = [
            Measurement(type=MeasurementType.COUNT, value=count, unit=Unit.COUNT),
        ]
    else:
        measurements = [
            Measurement(type=MeasurementType.COUNT, value=0.0, unit=Unit.COUNT),
        ]

    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=subsystem,
        protocol=Protocol.MOCK,
        timestamp=datetime.now(timezone.utc),
        measurements=measurements,
    )


SUBSYSTEM_DEVICES = {
    Subsystem.TEMP_HUMIDITY: ["sensor_dht22_01"],
    Subsystem.LIGHTING: ["sensor_pir_01"],
    Subsystem.GAS: ["sensor_mq2_01"],
    Subsystem.AGV: ["sensor_hcsr04_01"],
    Subsystem.COUNTING: ["sensor_ir_01"],
}


def publish_single(client: mqtt.Client, subsystem: Subsystem, device_id: str):
    msg = generate_message(device_id, subsystem)
    for m in msg.measurements:
        topic = f"factory/{subsystem.value}/sensors/{device_id}/{m.type.value}"
        payload = json.dumps(
            {"type": m.type.value, "value": m.value, "unit": m.unit.value}
        )
        client.publish(topic, payload)
    return msg


def run_mock(count: int = 0, interval: float = DEFAULT_INTERVAL):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
    client.loop_start()

    published = 0
    try:
        while True:
            for subsystem, devices in SUBSYSTEM_DEVICES.items():
                for device_id in devices:
                    publish_single(client, subsystem, device_id)
                    published += 1
                    if count > 0 and published >= count:
                        return
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Mock sensor data generator")
    parser.add_argument(
        "--count", type=int, default=0, help="Number of messages to send (0 = infinite)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="Interval between batches (seconds)",
    )
    args = parser.parse_args()
    run_mock(count=args.count, interval=args.interval)


if __name__ == "__main__":
    main()
