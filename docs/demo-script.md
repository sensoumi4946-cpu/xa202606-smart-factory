# Demonstration sequence

Use the commands in START_HERE.md. Enter the API key in the dashboard. Keep physical traffic and sample replay in separate test runs.

1. Show the domestic operating system version and running services. Only claim a tested OS/architecture.
2. Show one live observation from each connected subsystem. Identify MQTT, REST, Modbus and OPC UA from adapter logs, not only a JSON protocol label.
3. Show device aliases resolving to canonical IDs, valid units, rejected malformed records, and measurement timestamps.
4. Show gas, temperature, humidity, occupancy, lighting state, distance and count. Disconnect a sensor and show stale data.
5. Show a threshold warning and, separately, a trend forecast. Forecast output is not a validated failure probability.
6. Demonstrate remote control only on a configured physical receiver. Show an independent physical change and acknowledgment. MQTT publication alone proves neither.
7. If Fuseki is enabled, show RDF observations and the original timestamps. Test an outage and recovery before claiming durable semantic writes.
8. Present the completed hardware measurements and remaining limitations. Do not use sample JSON or historical benchmark snapshots as real-device accuracy evidence.
