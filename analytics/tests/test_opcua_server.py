from analytics.mock.opcua_server import next_distance


def test_next_distance_range():
    for _ in range(20):
        value = next_distance()
        assert 10.0 <= value <= 400.0
