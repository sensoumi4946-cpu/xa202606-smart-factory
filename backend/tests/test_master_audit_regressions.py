import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from analytics.anomaly_detector import AnomalyDetector
from backend import config, store
from backend.api import prediction
from backend.main import app
from backend.security.auth import validate_configuration
from connectivity.adapters.mqtt_adapter import MQTTAdapter
from smart_factory_contracts.messages import UnifiedMessage


def message(device='ESP32_001', subsystem='temp_humidity', measurements=None):
    return {
        'schema_version': 'v1', 'device_id': device, 'subsystem': subsystem,
        'protocol': 'mqtt', 'measurements': measurements or [
            {'type': 'temperature', 'value': 26.5, 'unit': 'celsius'},
            {'type': 'humidity', 'value': 60, 'unit': 'percent'},
        ],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATABASE_PATH', str(tmp_path / 'audit.db'))
    with TestClient(app) as client:
        yield client
    store.close_db()


def test_temperature_humidity_baselines_are_independent():
    detector = AnomalyDetector()
    for _ in range(10):
        detector.push_reading('sensor', 20, 'temperature')
        detector.push_reading('sensor', 80, 'humidity')
    result = detector.push_reading('sensor', 24, 'temperature')
    assert result.is_anomaly
    assert detector.sensor_stats('sensor', 'humidity')['mean'] == 80


def test_mqtt_accepts_actual_firmware_envelope():
    adapter = MQTTAdapter()
    parsed = adapter._parse_payload('factory/temp_humidity/sensors/ESP32_001/reading', json.dumps(message()))
    assert [m.value for m in parsed.measurements] == [26.5, 60]


def test_mqtt_does_not_invent_zero_when_value_missing():
    with pytest.raises(KeyError):
        MQTTAdapter()._parse_payload('factory/temp_humidity/sensors/ESP32_001/temperature', '{}')


@pytest.mark.asyncio
async def test_mqtt_callback_handoff_from_network_thread():
    adapter = MQTTAdapter()
    adapter._loop = asyncio.get_running_loop()
    incoming = SimpleNamespace(topic='factory/temp_humidity/sensors/ESP32_001/reading', payload=json.dumps(message()).encode())
    await asyncio.to_thread(adapter._on_message, None, None, incoming)
    parsed = await asyncio.wait_for(adapter.receive(), 1)
    assert len(parsed.measurements) == 2


def test_conflicting_sensor_identity_is_rejected(client):
    body = message(subsystem='lighting', measurements=[{'type': 'occupancy', 'value': 1, 'unit': 'boolean'}])
    assert client.post('/ingest/api/v1/data', json=body).status_code == 422


def test_nonfinite_readings_and_naive_time_rejected():
    body = message()
    body['measurements'][0]['value'] = float('nan')
    with pytest.raises(ValidationError):
        UnifiedMessage.model_validate(body)
    body = message()
    body['timestamp'] = '2026-09-05T12:00:00'
    with pytest.raises(ValidationError):
        UnifiedMessage.model_validate(body)


def test_record_id_matches_provenance_id_and_health_is_updated(client):
    response = client.post('/ingest/api/v1/data', json=message())
    assert response.status_code == 200
    body = response.json()
    assert body['record_id'] == body['ingest_id']
    assert body['kg_write'] == 'disabled'
    health = client.get('/api/v1/devices/ESP32_001/health').json()
    assert health['message_count'] == 1


def test_reading_route_preserves_timestamp_and_runs_prediction(client, monkeypatch):
    calls = []
    monkeypatch.setattr('backend.api.ingest.run_prediction_pipeline', lambda *a, **kw: calls.append((a, kw)))
    stamp = datetime.now(timezone.utc) - timedelta(minutes=2)
    body = dict(sensor_id='ESP32_001', subsystem='temp_humidity', protocol='mqtt', property_name='temperature', value=26, unit='celsius', timestamp=stamp.isoformat())
    response = client.post('/ingest/reading', json=body)
    assert response.status_code == 200
    assert calls[0][1]['timestamp'] == stamp.timestamp()
    assert store.get_sensor_record(response.json()['record_id'])['timestamp'] == stamp.isoformat()


@pytest.mark.asyncio
async def test_recovered_reading_clears_old_prediction():
    await prediction.reset_analytics()
    prediction.process_reading('test', 'temp_humidity', 'mqtt', [{'type': 'temperature', 'value': 90}])
    assert (await prediction.list_predictions())['total'] == 1
    prediction.process_reading('test', 'temp_humidity', 'mqtt', [{'type': 'temperature', 'value': 20}])
    assert (await prediction.list_predictions())['total'] == 0
    await prediction.reset_analytics()


@pytest.mark.parametrize('api,signing', [('', ''), ('CHANGE_ME_' * 5, 'x'*40), ('a'*40, 'a'*40)])
def test_real_profile_refuses_missing_placeholder_or_shared_keys(monkeypatch, api, signing):
    monkeypatch.setenv('HARDWARE_PROFILE', 'real')
    monkeypatch.setenv('API_KEY', api)
    monkeypatch.setenv('COMMAND_SIGNING_KEY', signing)
    with pytest.raises(RuntimeError):
        validate_configuration()


def test_real_profile_accepts_independent_keys(monkeypatch):
    monkeypatch.setenv('HARDWARE_PROFILE', 'real')
    monkeypatch.setenv('API_KEY', 'a'*40)
    monkeypatch.setenv('COMMAND_SIGNING_KEY', 'b'*40)
    validate_configuration()


def test_actual_firmware_status_fields_pass_semantic_gate(client):
    body = message()
    body['measurements'] += [{'type': p, 'value': 0, 'unit': 'status'} for p in ('device_status', 'error_code', 'sensor_status')]
    assert client.post('/ingest/api/v1/data', json=body).status_code == 200


def test_active_protocol_profile_omits_absent_dht_opcua_nodes(monkeypatch):
    from connectivity.generated_adapters import load_adapter_set
    monkeypatch.setenv('ACTIVE_PROTOCOL_DEVICES', json.dumps({'opcua': ['ESP32_004']}))
    plans = load_adapter_set().opcua_nodes()
    assert plans and all(p['device_id'] == 'ESP32_004' for p in plans)


def test_modbus_receive_queue_is_bounded():
    from connectivity.adapters.modbus_adapter import ModbusAdapter
    assert ModbusAdapter()._ensure_queue().maxsize == 1


def test_retry_record_lookup_keeps_original_observation(client):
    first = client.post('/ingest/api/v1/data', json=message()).json()['record_id']
    body = message()
    body['measurements'][0]['value'] = 30
    client.post('/ingest/api/v1/data', json=body)
    assert store.get_sensor_record(first)['measurements'][0]['value'] == 26.5


def test_enrolled_device_key_is_scoped_to_its_sensor(client, monkeypatch):
    from backend.security import auth, device_keys
    enrollment = device_keys.enroll_device('ESP32_001', ['ingest'])
    monkeypatch.setattr(auth, '_AUTH_DISABLED', False)
    headers = {'X-API-Key': enrollment['api_key']}
    assert client.post('/ingest/api/v1/data', json=message(), headers=headers).status_code == 200
    assert client.get('/api/v1/security/whoami', headers=headers).status_code == 200
    assert client.post('/ingest/api/v1/data', json=message(device='ESP32_999'), headers=headers).status_code == 403
    assert client.post('/api/v1/security/devices/enroll', json={'device_id':'other'}, headers=headers).status_code == 403
    device_keys.revoke_key(enrollment['key_id'])
    assert client.post('/ingest/api/v1/data', json=message(), headers=headers).status_code == 401
