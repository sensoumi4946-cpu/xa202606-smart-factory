# Device-side agent for the remote-control loop.


import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
import time

import paho.mqtt.client as mqtt
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("actuator")

# Whatever the board can actually do
SUPPORTED_ACTIONS = {"on", "off", "toggle", "dim", "reset"}


class ActuatorAgent:
    def __init__(
        self,
        device_id,
        subsystem,
        broker_host,
        broker_port,
        api_key="",
        signing_key="",
    ):
        self.device_id = device_id
        self.subsystem = subsystem
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.api_key = api_key
        self.signing_key = signing_key
        self.topic = f"factory/{subsystem}/control/{device_id}"
        self.relay_state = "off"

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"actuator-{device_id}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def run(self):
        log.info("connecting to %s:%s", self.broker_host, self.broker_port)
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_forever()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            log.error("broker refused connection: %s", reason_code)
            return
        client.subscribe(self.topic, qos=1)
        log.info("listening on %s", self.topic)
        log.info("relay is %s", self.relay_state)

    def _on_message(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("dropped an unparseable payload on %s", msg.topic)
            return

        command_id = cmd.get("command_id")
        action = cmd.get("action")
        params = cmd.get("params") or {}
        ack_url = cmd.get("ack_url")

        if not command_id or not action:
            log.warning("command missing command_id or action, ignoring")
            return

        if self.signing_key and not self._valid_signature(cmd):
            log.warning("command %s has an invalid signature", command_id[:8])
            return

        log.info("got '%s' (command_id=%s)", action, command_id[:8])
        ok, detail = self._actuate(action, params)
        log.info("  -> %s | %s", "OK" if ok else "FAILED", detail)

        if ack_url:
            self._send_ack(ack_url, ok, detail)

    def _valid_signature(self, command):
        params = json.dumps(
            command.get("params") or {},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        canonical = "|".join(
            [
                str(command.get("command_id", "")),
                str(command.get("device_id", "")),
                str(command.get("action", "")),
                params,
                str(command.get("issued_at", "")),
                str(command.get("nonce", "")),
            ]
        )
        expected = hmac.new(
            self.signing_key.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, str(command.get("signature", "")))

    def _actuate(self, action, params):
        if action not in SUPPORTED_ACTIONS:
            return False, f"unsupported action '{action}'"

        if action == "on":
            self.relay_state = "on"
        elif action == "off":
            self.relay_state = "off"
        elif action == "toggle":
            self.relay_state = "off" if self.relay_state == "on" else "on"
        elif action == "dim":
            level = params.get("brightness")
            if not isinstance(level, (int, float)) or not 0 <= level <= 100:
                return False, "brightness must be a number between 0 and 100"
            self.relay_state = f"dim:{int(level)}"
        elif action == "reset":
            self.relay_state = "off"

        # A real relay takes a few tens of milliseconds to settle
        time.sleep(0.15)
        return True, f"relay={self.relay_state}"

    def _send_ack(self, ack_url, success, detail):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        try:
            resp = requests.post(
                ack_url,
                json={"success": success, "detail": detail},
                headers=headers,
                timeout=5,
            )
            if resp.status_code != 200:
                log.warning(
                    "ack rejected: HTTP %s %s", resp.status_code, resp.text[:120]
                )
        except requests.RequestException as exc:
            log.warning("could not reach backend for ack: %s", exc)


def main():
    parser = argparse.ArgumentParser(description="Simulated actuator device")
    parser.add_argument("--device-id", default="relay_lighting_01")
    parser.add_argument("--subsystem", default="lighting")
    parser.add_argument(
        "--broker-host", default=os.getenv("MQTT_BROKER_HOST", "localhost")
    )
    parser.add_argument(
        "--broker-port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", "1883"))
    )
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--signing-key", default=os.getenv("COMMAND_SIGNING_KEY", ""))
    args = parser.parse_args()

    agent = ActuatorAgent(
        device_id=args.device_id,
        subsystem=args.subsystem,
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        api_key=args.api_key,
        signing_key=args.signing_key,
    )
    try:
        agent.run()
    except KeyboardInterrupt:
        log.info("stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
