# Tests for sparql_templates.py

from semantic_layer.sparql_templates import (
    NAMED_QUERIES,
    cross_subsystem_correlation,
    device_property_matrix,
    latest_by_device,
    observations_in_window,
    provenance_trace,
    subsystem_summary,
)


# latest_by_device

def test_latest_by_device_contains_device_uri():
    q = latest_by_device("sensor_dht22_01")
    assert "sensor_dht22_01" in q
    assert "sosa:madeBySensor" in q


def test_latest_by_device_respects_limit():
    q = latest_by_device("sensor_mq2_01", limit=5)
    assert "LIMIT 5" in q


def test_latest_by_device_has_prefixes():
    q = latest_by_device("sensor_dht22_01")
    assert "PREFIX sosa:" in q
    assert "PREFIX sf:" in q


# observations_in_window

def test_window_query_has_time_filter():
    q = observations_in_window(minutes=15)
    assert "PT15M" in q
    assert "FILTER" in q


def test_window_default_is_30_min():
    q = observations_in_window()
    assert "PT30M" in q


def test_window_query_selects_subsystem():
    q = observations_in_window()
    assert "?subsystem" in q


# subsystem_summary

def test_subsystem_summary_uses_group_by():
    q = subsystem_summary()
    assert "GROUP BY" in q
    assert "?subsystem" in q


def test_subsystem_summary_counts_sensors():
    q = subsystem_summary()
    assert "COUNT" in q
    assert "?sensorCount" in q or "sensorCount" in q


# device_property_matrix

def test_matrix_query_is_valid_sparql():
    q = device_property_matrix()
    assert "SELECT" in q
    assert "WHERE" in q
    # should be grouping by sensor and property
    assert "?sensor" in q
    assert "?prop" in q


# cross_subsystem_correlation

def test_correlation_contains_both_properties():
    q = cross_subsystem_correlation("measuresTemperature", "measuresCO")
    assert "measuresTemperature" in q
    assert "measuresCO" in q


def test_correlation_has_time_window():
    q = cross_subsystem_correlation("measuresTemperature", "measuresCO", minutes=5)
    assert "PT5M" in q


def test_correlation_uses_different_sensors():
    q = cross_subsystem_correlation("measuresTemperature", "measuresCO")
    # should have a FILTER to ensure sensorA != sensorB
    assert "sensorA" in q
    assert "sensorB" in q
    assert "FILTER" in q


# provenance_trace

def test_provenance_query_has_prov_prefix():
    q = provenance_trace("sensor_dht22_01")
    assert "PREFIX prov:" in q
    assert "prov:wasAttributedTo" in q or "prov:generatedAtTime" in q


def test_provenance_query_targets_device():
    q = provenance_trace("sensor_mq2_01")
    assert "sensor_mq2_01" in q


# NAMED_QUERIES registry

def test_named_queries_are_callable():
    for name, fn in NAMED_QUERIES.items():
        q = fn()
        assert isinstance(q, str)
        assert len(q) > 50 
        assert "SELECT" in q


def test_named_queries_has_expected_keys():
    assert "subsystem-summary" in NAMED_QUERIES
    assert "device-property-matrix" in NAMED_QUERIES
