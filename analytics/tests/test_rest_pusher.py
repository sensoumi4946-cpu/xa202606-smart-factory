from analytics.mock.rest_pusher import make_counting_payload, make_lighting_payload


def test_make_lighting_payload():
    payload = make_lighting_payload(active=True)
    assert payload == {
        "device": "sensor_pir_01",
        "metrics": {"occupancy": "active", "light": "on"},
    }


def test_make_counting_payload():
    payload = make_counting_payload(count=42)
    assert payload == {"d": "sensor_ir_01", "v": 42}
