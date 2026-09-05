# UnifiedMessage → RDF triples mapping.
#
# Converts a UnifiedMessage into an rdflib.Graph containing SOSA
# Observation instances. Not wired into the backend runtime — this
# module is verified exclusively through pytest + local SPARQL queries.
import uuid as _uuid
from datetime import timezone

from rdflib import RDF, XSD, Graph, Literal, SOSA, URIRef
from smart_factory_contracts.messages import MeasurementType, Subsystem, UnifiedMessage

SF = "http://example.org/smart-factory#"

TYPE_TO_PROPERTY: dict[MeasurementType, URIRef] = {
    MeasurementType.TEMPERATURE: URIRef(f"{SF}measuresTemperature"),
    MeasurementType.HUMIDITY: URIRef(f"{SF}measuresHumidity"),
    MeasurementType.SMOKE: URIRef(f"{SF}measuresSmoke"),
    MeasurementType.CO: URIRef(f"{SF}measuresCO"),
    MeasurementType.COMBUSTIBLE_GAS: URIRef(f"{SF}measuresCombustibleGas"),
    MeasurementType.DISTANCE: URIRef(f"{SF}measuresDistance"),
    MeasurementType.COUNT: URIRef(f"{SF}measuresCount"),
    MeasurementType.OCCUPANCY: URIRef(f"{SF}measuresOccupancy"),
    MeasurementType.LIGHT_STATE: URIRef(f"{SF}measuresLightState"),
    MeasurementType.DEVICE_STATUS: URIRef(f"{SF}measuresDeviceStatus"),
    MeasurementType.ERROR_CODE: URIRef(f"{SF}measuresErrorCode"),
    MeasurementType.SENSOR_STATUS: URIRef(f"{SF}measuresSensorStatus"),
}

TYPE_TO_SENSOR_CLASS: dict[MeasurementType, URIRef] = {
    MeasurementType.TEMPERATURE: URIRef(f"{SF}TemperatureSensor"),
    MeasurementType.HUMIDITY: URIRef(f"{SF}HumiditySensor"),
    MeasurementType.SMOKE: URIRef(f"{SF}GasSensor"),
    MeasurementType.CO: URIRef(f"{SF}GasSensor"),
    MeasurementType.COMBUSTIBLE_GAS: URIRef(f"{SF}GasSensor"),
    MeasurementType.DISTANCE: URIRef(f"{SF}ProximitySensor"),
    MeasurementType.COUNT: URIRef(f"{SF}CountSensor"),
    MeasurementType.OCCUPANCY: URIRef(f"{SF}OccupancySensor"),
    MeasurementType.LIGHT_STATE: URIRef(f"{SF}ActuatorStateSensor"),
    MeasurementType.DEVICE_STATUS: URIRef(f"{SF}DeviceStatusSensor"),
    MeasurementType.ERROR_CODE: URIRef(f"{SF}DeviceStatusSensor"),
    MeasurementType.SENSOR_STATUS: URIRef(f"{SF}DeviceStatusSensor"),
}

SUBSYSTEM_TO_RESOURCE: dict[Subsystem, URIRef] = {
    Subsystem.TEMP_HUMIDITY: URIRef(f"{SF}TempHumiditySubsystem"),
    Subsystem.LIGHTING: URIRef(f"{SF}LightingSubsystem"),
    Subsystem.GAS: URIRef(f"{SF}GasMonitoringSubsystem"),
    Subsystem.AGV: URIRef(f"{SF}AGVObstacleSubsystem"),
    Subsystem.COUNTING: URIRef(f"{SF}CountingSubsystem"),
}


def to_rdf_graph(msg: UnifiedMessage) -> Graph:
    """Convert a UnifiedMessage to an RDFlib Graph with Observation triples."""
    g = Graph()
    device_uri = URIRef(f"{SF}{msg.device_id}")
    belongs = URIRef(f"{SF}belongsToSubsystem")
    has_unit = URIRef(f"{SF}hasUnit")
    via = URIRef(f"{SF}transportedVia")

    g.add((device_uri, RDF.type, SOSA.Sensor))
    for m in msg.measurements:
        sensor_class = TYPE_TO_SENSOR_CLASS.get(m.type)
        if sensor_class is not None:
            g.add((device_uri, RDF.type, sensor_class))

    subsys_resource = SUBSYSTEM_TO_RESOURCE.get(msg.subsystem)
    if subsys_resource is not None:
        g.add((device_uri, belongs, subsys_resource))

    g.add((device_uri, via, Literal(msg.protocol.value)))

    for m in msg.measurements:
        obs_uri = URIRef(f"{SF}obs_{_uuid.uuid4().hex[:8]}")
        g.add((obs_uri, RDF.type, SOSA.Observation))
        g.add((obs_uri, SOSA.madeBySensor, device_uri))

        prop = TYPE_TO_PROPERTY[m.type]
        g.add((obs_uri, SOSA.observedProperty, prop))
        g.add((obs_uri, SOSA.hasSimpleResult, Literal(m.value, datatype=XSD.double)))
        g.add((obs_uri, has_unit, Literal(m.unit.value)))

        ts = (
            msg.timestamp
            if msg.timestamp.tzinfo is not None
            else msg.timestamp.replace(tzinfo=timezone.utc)
        )
        g.add(
            (obs_uri, SOSA.resultTime, Literal(ts.isoformat(), datatype=XSD.dateTime))
        )

    return g
