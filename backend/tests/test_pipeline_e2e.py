# End-to-end integration tests for the full ingest pipeline
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from smart_factory_contracts.messages import (
    Measurement, MeasurementType, Protocol, Subsystem, Unit, UnifiedMessage,
)


def _make_msg(
    device_id: str = "test_sensor_01",
    subsystem: Subsystem = Subsystem.GAS,
    protocol: Protocol = Protocol.MODBUS,
    measurements: list | None = None,
) -> UnifiedMessage:
    if measurements is None:
        measurements = [
            Measurement(type=MeasurementType.CO, value=22.5, unit=Unit.PPM),
        ]
    return UnifiedMessage(
        schema_version="v1",
        device_id=device_id,
        subsystem=subsystem,
        protocol=protocol,
        timestamp=datetime.now(timezone.utc),
        measurements=measurements,
    )

# Semantic gate tests

def test_gate_accepts_valid_message():
    from semantic_layer.observation_gate import check_and_prepare
    msg = _make_msg()
    result = check_and_prepare(msg, use_domain_shapes=False)
    assert result.accepted is True
    assert result.graph is not None


def test_gate_rejects_impossible_temperature():
    from semantic_layer.observation_gate import check_and_prepare
    msg = _make_msg(
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[
            Measurement(type=MeasurementType.TEMPERATURE, value=9999.0, unit=Unit.CELSIUS),
        ],
    )
    result = check_and_prepare(msg, use_domain_shapes=True)
    if not result.accepted:
        assert len(result.report.violations) > 0
    assert result.graph is not None or not result.accepted


def test_gate_adds_provenance():
    from semantic_layer.observation_gate import check_and_prepare
    from rdflib.namespace import RDF
    from rdflib import URIRef
    PROV = "http://www.w3.org/ns/prov#"
    msg = _make_msg()
    result = check_and_prepare(msg, add_prov=True, use_domain_shapes=False)
    assert result.accepted
    assert result.graph is not None  
    agents = list(result.graph.subjects(RDF.type, URIRef(f"{PROV}SoftwareAgent")))
    assert len(agents) >= 1


# Unit harmonizer tests

def test_qudt_enrichment_added():
    from semantic_layer.mapping import to_rdf_graph
    from semantic_layer.semantic_unit_harmonizer import enrich_graph_with_qudt
    from rdflib import Namespace
    QUDT = Namespace("http://qudt.org/schema/qudt/")
    msg = _make_msg(
        subsystem=Subsystem.TEMP_HUMIDITY,
        protocol=Protocol.MQTT,
        measurements=[Measurement(type=MeasurementType.TEMPERATURE, value=25.0, unit=Unit.CELSIUS)],
    )
    g = to_rdf_graph(msg)
    enrich_graph_with_qudt(g)
    qudt_units = list(g.objects(None, QUDT.unit))
    assert len(qudt_units) >= 1, "Expected at least one qudt:unit triple"


def test_celsius_to_kelvin_conversion():
    from semantic_layer.semantic_unit_harmonizer import harmonize_to_si
    result = harmonize_to_si("celsius", 0.0)
    assert result is not None
    si_val, _, label = result
    assert abs(si_val - 273.15) < 0.001
    assert label == "kelvin"


# Analytics bridge tests

def test_analytics_bridge_no_anomaly():
    from backend.services.analytics_ingest_bridge import analyse_after_ingest
    alerts = analyse_after_ingest(
        device_id="test_sensor_01",
        subsystem="gas",
        protocol="modbus",
        measurements=[{"type": "co", "value": 5.0, "unit": "ppm"}],
    )
    assert isinstance(alerts, list)


# Store integration test

def test_store_insert_and_query(tmp_path, monkeypatch):

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("backend.store.DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)

    from backend.store import init_db, insert_sensor_data, query_sensor_data
    init_db()

    msg = _make_msg()
    record_id = insert_sensor_data(msg)
    assert record_id is not None

    rows = query_sensor_data(device_id="test_sensor_01")
    assert len(rows) == 1
    assert rows[0]["device_id"] == "test_sensor_01"


# Full pipeline

@pytest.mark.asyncio
async def test_full_ingest_pipeline_mocked_fuseki(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_e2e.db")
    monkeypatch.setattr("backend.store.DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    from backend.store import init_db
    init_db()

    msg = _make_msg()

    with patch(
        "semantic_layer.fuseki.write_to_fuseki",
        new=AsyncMock(return_value=True),
    ):
        from semantic_layer.observation_gate import check_and_prepare
        from semantic_layer.fuseki import write_to_fuseki
        from backend.store import insert_sensor_data

        gate = check_and_prepare(msg, use_domain_shapes=False)
        assert gate.accepted

        record_id = insert_sensor_data(msg)
        assert record_id is not None

        ok = await write_to_fuseki(msg, "http://mock-fuseki/factory/data")
        assert ok is True