import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend import config, db
from backend.main import app
from backend.middleware import TokenBucket, limiter, metrics
from backend.services import device_health
from backend.store import init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    path = tmp_path / "infra.db"
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(path))
    monkeypatch.setattr("backend.store.DATABASE_PATH", str(path))
    init_db()
    yield path


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestSchema:
    def test_migrations_reach_current_version(self):
        assert db.schema_version() == db.SCHEMA_VERSION

    def test_migrations_are_idempotent(self):
        before = db.schema_version()
        db.ensure_schema()
        db.ensure_schema()
        assert db.schema_version() == before

    def test_every_version_has_statements(self):
        for version in range(1, db.SCHEMA_VERSION + 1):
            assert db.MIGRATIONS.get(version), f"migration {version} is empty"

    def test_core_tables_exist(self):
        with db.connection() as conn:
            names = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        for table in (
            "sensor_data",
            "alerts",
            "control_commands",
            "device_keys",
            "command_audit",
            "device_health",
        ):
            assert table in names

    def test_wal_is_enabled(self):
        with db.connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"


class TestPool:
    def test_connections_are_reused(self):
        with db.connection() as conn:
            first = id(conn)
        with db.connection() as conn:
            second = id(conn)
        assert first == second

    def test_pool_does_not_grow_without_bound(self):
        held = []
        for _ in range(4):
            ctx = db.connection()
            held.append((ctx, ctx.__enter__()))
        for ctx, _ in held:
            ctx.__exit__(None, None, None)
        assert db.pool_stats()["created"] <= db.POOL_SIZE

    def test_path_is_resolved_per_call(self, tmp_path, monkeypatch):
        other = tmp_path / "other.db"
        monkeypatch.setattr("backend.config.DATABASE_PATH", str(other))
        with db.connection() as conn:
            conn.execute("SELECT 1")
        assert db.pool_stats()["path"] == str(other)

    def test_transaction_rolls_back_on_error(self):
        with pytest.raises(ValueError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO device_health (device_id) VALUES ('rollback_me')"
                )
                raise ValueError("boom")
        with db.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM device_health WHERE device_id = 'rollback_me'"
            ).fetchone()
        assert row is None


class TestRateLimit:
    def test_burst_is_allowed(self):
        bucket = TokenBucket(rate_per_minute=60, burst=5)
        assert all(bucket.allow("a") for _ in range(5))

    def test_burst_is_then_exhausted(self):
        bucket = TokenBucket(rate_per_minute=60, burst=3)
        for _ in range(3):
            bucket.allow("a")
        assert bucket.allow("a") is False

    def test_clients_have_separate_buckets(self):
        bucket = TokenBucket(rate_per_minute=60, burst=2)
        bucket.allow("a")
        bucket.allow("a")
        assert bucket.allow("a") is False
        assert bucket.allow("b") is True

    @pytest.mark.asyncio
    async def test_flood_is_rejected_with_429(self, monkeypatch):
        monkeypatch.setattr("backend.middleware.limiter", TokenBucket(60, 3))
        async with await _client() as c:
            statuses = [
                (await c.get("/api/v1/devices")).status_code for _ in range(6)
            ]
        assert 429 in statuses

    @pytest.mark.asyncio
    async def test_health_is_never_rate_limited(self, monkeypatch):
        monkeypatch.setattr("backend.middleware.limiter", TokenBucket(60, 1))
        async with await _client() as c:
            for _ in range(5):
                assert (await c.get("/health")).status_code == 200


class TestRequestLimits:
    @pytest.mark.asyncio
    async def test_oversized_body_is_rejected(self):
        payload = {"schema_version": "v1", "junk": "x" * 200_000}
        async with await _client() as c:
            resp = await c.post("/ingest/api/v1/data", json=payload)
        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_normal_body_is_accepted(self):
        payload = {
            "schema_version": "v1",
            "device_id": "ESP32_001_dht22",
            "subsystem": "temp_humidity",
            "protocol": "mqtt",
            "measurements": [
                {"type": "temperature", "value": 26.1, "unit": "celsius"}
            ],
        }
        async with await _client() as c:
            resp = await c.post("/ingest/api/v1/data", json=payload)
        assert resp.status_code == 200


class TestObservability:
    @pytest.mark.asyncio
    async def test_every_response_carries_a_request_id(self):
        async with await _client() as c:
            resp = await c.get("/health")
        assert resp.headers.get("X-Request-ID")

    @pytest.mark.asyncio
    async def test_supplied_request_id_is_echoed(self):
        async with await _client() as c:
            resp = await c.get("/health", headers={"X-Request-ID": "trace-abc"})
        assert resp.headers["X-Request-ID"] == "trace-abc"

    @pytest.mark.asyncio
    async def test_response_time_header_present(self):
        async with await _client() as c:
            resp = await c.get("/health")
        assert float(resp.headers["X-Response-Time-Ms"]) >= 0

    @pytest.mark.asyncio
    async def test_metrics_report_latency_percentiles(self):
        async with await _client() as c:
            for _ in range(5):
                await c.get("/api/v1/devices")
            resp = await c.get("/metrics")
        body = resp.json()
        assert body["requests_total"] >= 5
        assert "p99" in body["latency_ms"]
        assert body["database"]["schema_version"] == db.SCHEMA_VERSION

    @pytest.mark.asyncio
    async def test_metrics_count_rate_limit_rejections(self, monkeypatch):
        monkeypatch.setattr("backend.middleware.limiter", TokenBucket(60, 2))
        async with await _client() as c:
            for _ in range(5):
                await c.get("/api/v1/devices")
            body = (await c.get("/metrics")).json()
        assert body["rejected_rate_limit"] >= 1


class TestDeviceHealth:
    def test_all_normal_is_healthy(self):
        decoded = device_health.decode_status_registers([0, 0, 0])
        assert decoded["healthy"] is True
        assert decoded["device_status_label"] == "正常"

    def test_fault_status_is_critical(self):
        decoded = device_health.decode_status_registers([3, 1, 0])
        assert decoded["severity"] == "critical"
        assert decoded["error_label"] == "读取超时"

    def test_sensor_disconnected_is_reported(self):
        decoded = device_health.decode_status_registers([2, 0, 3])
        assert decoded["sensor_key"] == "disconnected"
        assert decoded["healthy"] is False

    def test_unknown_codes_do_not_crash(self):
        decoded = device_health.decode_status_registers([99, 99, 99])
        assert decoded["device_status_key"] == "unknown"

    def test_short_block_raises(self):
        with pytest.raises(ValueError):
            device_health.decode_status_registers([0, 0])

    def test_network_fault_distinguished_from_sensor_fault(self):
        wifi = device_health.decode_status_registers([2, 3, 0])
        assert device_health.diagnose(wifi, reachable=False)["verdict"] == "network"

        sensor = device_health.decode_status_registers([2, 0, 3])
        assert device_health.diagnose(sensor, reachable=True)["verdict"] == "sensor"

    def test_warming_up_is_not_a_fault(self):
        decoded = device_health.decode_status_registers([1, 0, 1])
        assert device_health.diagnose(decoded, reachable=True)["verdict"] == "warming_up"

    def test_calibration_advice_mentions_gas_sensors(self):
        decoded = device_health.decode_status_registers([0, 0, 2])
        assert "标定" in device_health.diagnose(decoded, reachable=True)["advice"]

    def test_health_is_persisted_and_counted(self):
        device_health.record_health("ESP32_002_mq2", [0, 0, 0], firmware="v1.2.0")
        device_health.record_health("ESP32_002_mq2", [3, 1, 0])
        record = device_health.get_health("ESP32_002_mq2")
        assert record is not None
        assert record["message_count"] == 2
        assert record["firmware"] == "v1.2.0"
        assert record["device_status"] == 3

    def test_first_seen_is_not_overwritten(self):
        device_health.record_health("ESP32_003_pir", [0, 0, 0])
        first = device_health.get_health("ESP32_003_pir")["first_seen"]
        device_health.record_health("ESP32_003_pir", [0, 0, 0])
        assert device_health.get_health("ESP32_003_pir")["first_seen"] == first


class TestDeviceDetailApi:
    @pytest.mark.asyncio
    async def test_detail_endpoint_returns_items(self):
        device_health.record_health("ESP32_001_dht22", [0, 0, 0], firmware="v1.2.0")
        async with await _client() as c:
            resp = await c.get("/api/v1/devices/detail")
        body = resp.json()
        assert resp.status_code == 200
        assert body["total"] >= 1
        entry = next(i for i in body["items"] if i["device_id"] == "ESP32_001_dht22")
        assert entry["firmware"] == "v1.2.0"
        assert "diagnosis" in entry

    @pytest.mark.asyncio
    async def test_devices_without_health_still_listed(self):
        payload = {
            "schema_version": "v1",
            "device_id": "ESP32_009_new",
            "subsystem": "counting",
            "protocol": "rest",
            "measurements": [{"type": "count", "value": 1, "unit": "count"}],
        }
        async with await _client() as c:
            await c.post("/ingest/api/v1/data", json=payload)
            body = (await c.get("/api/v1/devices/detail")).json()
        entry = next(i for i in body["items"] if i["device_id"] == "ESP32_009_new")
        assert entry["device_status_label"] == "待上报"

    @pytest.mark.asyncio
    async def test_health_report_endpoint(self):
        async with await _client() as c:
            resp = await c.post(
                "/api/v1/devices/ESP32_002_mq2/health"
                "?device_status=3&error_code=1&sensor_status=3"
            )
        assert resp.status_code == 200
        assert resp.json()["sensor_key"] == "disconnected"

    @pytest.mark.asyncio
    async def test_unknown_device_health_is_404(self):
        async with await _client() as c:
            resp = await c.get("/api/v1/devices/nobody/health")
        assert resp.status_code == 404
