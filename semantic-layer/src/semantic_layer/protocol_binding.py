from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Any, Optional

from rdflib import Graph, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")

SUPPORTED_PROTOCOLS = ("modbus", "opcua", "mqtt", "rest")

WORD_ORDERS = ("big", "little")
BYTE_ORDERS = ("big", "little")

SUBSYSTEM_SUFFIX = "_subsystem"

DEFAULT_FUNCTION_CODE = 3

REGISTER_TYPES = {
    "int16": (1, "h"),
    "uint16": (1, "H"),
    "int32": (2, "i"),
    "uint32": (2, "I"),
    "float32": (2, "f"),
}

BINDING_SHAPE_TTL = '''
@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix sf:   <http://example.org/smart-factory#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

sf:ProtocolBindingShape a sh:NodeShape ;
    sh:targetClass sf:ProtocolBinding ;
    sh:property [
        sh:path sf:bindsProperty ;
        sh:minCount 1 ; sh:maxCount 1 ; sh:nodeKind sh:IRI ;
        sh:message "binding must reference exactly one sf:bindsProperty" ;
    ] ;
    sh:property [
        sh:path sf:transportProtocol ;
        sh:minCount 1 ; sh:maxCount 1 ;
        sh:in ( "modbus" "opcua" "mqtt" "rest" ) ;
        sh:message "transportProtocol must be modbus, opcua, mqtt or rest" ;
    ] ;
    sh:property [
        sh:path sf:deviceId ;
        sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:string ;
        sh:message "binding must declare exactly one sf:deviceId" ;
    ] ;
    sh:property [
        sh:path sf:deviceAlias ;
        sh:datatype xsd:string ;
        sh:message "deviceAlias must be an xsd:string" ;
    ] ;
    sh:property [
        sh:path sf:pollIntervalMs ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:minInclusive 50 ;
        sh:message "pollIntervalMs must be an integer of at least 50" ;
    ] ;
    sh:property [
        sh:path sf:scaleFactor ;
        sh:maxCount 1 ; sh:datatype xsd:double ;
        sh:message "scaleFactor must be a single xsd:double" ;
    ] ;
    sh:property [
        sh:path sf:registerAddress ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:minInclusive 0 ;
        sh:message "registerAddress must be a non-negative integer" ;
    ] ;
    sh:property [
        sh:path sf:registerBase ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:minInclusive 0 ;
        sh:message "registerBase must be a non-negative integer" ;
    ] ;
    sh:property [
        sh:path sf:functionCode ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:minInclusive 1 ; sh:maxInclusive 4 ;
        sh:message "functionCode must be a modbus read code between 1 and 4" ;
    ] ;
    sh:property [
        sh:path sf:wordOrder ;
        sh:maxCount 1 ; sh:in ( "big" "little" ) ;
        sh:message "wordOrder must be big or little" ;
    ] ;
    sh:property [
        sh:path sf:byteOrder ;
        sh:maxCount 1 ; sh:in ( "big" "little" ) ;
        sh:message "byteOrder must be big or little" ;
    ] .

sf:ModbusBindingShape a sh:NodeShape ;
    sh:targetClass sf:ProtocolBinding ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:message "modbus binding must declare sf:registerAddress" ;
        sh:select """
            SELECT $this
            WHERE {
                $this <http://example.org/smart-factory#transportProtocol> "modbus" .
                FILTER NOT EXISTS {
                    $this <http://example.org/smart-factory#registerAddress> ?address .
                }
            }
        """ ;
    ] .

sf:OpcuaBindingShape a sh:NodeShape ;
    sh:targetClass sf:ProtocolBinding ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:message "opcua binding must declare sf:nodeId" ;
        sh:select """
            SELECT $this
            WHERE {
                $this <http://example.org/smart-factory#transportProtocol> "opcua" .
                FILTER NOT EXISTS {
                    $this <http://example.org/smart-factory#nodeId> ?node .
                }
            }
        """ ;
    ] .
'''


def _local(uri: Any) -> str:
    text = str(uri)
    if "#" in text:
        text = text.rsplit("#", 1)[-1]
    elif "/" in text:
        text = text.rsplit("/", 1)[-1]
    if text.startswith("measures"):
        text = text[len("measures") :]
    out = []
    for i, ch in enumerate(text):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def canonical_subsystem(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if "#" in text or "/" in text or any(ch.isupper() for ch in text):
        text = _local(text)
    if text.endswith(SUBSYSTEM_SUFFIX):
        text = text[: -len(SUBSYSTEM_SUFFIX)]
    return text


@dataclass
class ProtocolBinding:
    binding_id: str
    device_id: str
    property_name: str
    protocol: str
    subsystem: str = ""
    unit: str = ""
    poll_interval_ms: int = 2000
    scale_factor: float = 1.0
    offset: float = 0.0
    register_address: Optional[int] = None
    register_base: int = 0
    register_count: int = 1
    register_type: str = "uint16"
    function_code: int = DEFAULT_FUNCTION_CODE
    word_order: str = "big"
    byte_order: str = "big"
    slave_id: int = 1
    node_id: str = ""
    namespace_index: int = 2
    topic: str = ""
    qos: int = 1
    path: str = ""
    method: str = "POST"
    device_aliases: list[str] = field(default_factory=list)

    @property
    def wire_address(self) -> Optional[int]:
        if self.register_address is None:
            return None
        return self.register_base + self.register_address

    @property
    def canonical_subsystem(self) -> str:
        return canonical_subsystem(self.subsystem)

    def matches_device(self, candidate: Any) -> bool:
        target = str(candidate or "").strip().lower()
        if not target:
            return False
        if target == self.device_id.strip().lower():
            return True
        return any(target == str(a).strip().lower() for a in self.device_aliases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "device_id": self.device_id,
            "device_aliases": list(self.device_aliases),
            "property_name": self.property_name,
            "protocol": self.protocol,
            "subsystem": self.subsystem,
            "canonical_subsystem": self.canonical_subsystem,
            "unit": self.unit,
            "poll_interval_ms": self.poll_interval_ms,
            "scale_factor": self.scale_factor,
            "offset": self.offset,
            "register_address": self.register_address,
            "register_base": self.register_base,
            "wire_address": self.wire_address,
            "register_count": self.register_count,
            "register_type": self.register_type,
            "function_code": self.function_code,
            "word_order": self.word_order,
            "byte_order": self.byte_order,
            "slave_id": self.slave_id,
            "node_id": self.node_id,
            "namespace_index": self.namespace_index,
            "topic": self.topic,
            "qos": self.qos,
            "path": self.path,
            "method": self.method,
        }


@dataclass
class BindingLoadResult:
    accepted: bool
    bindings_added: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "bindings_added": self.bindings_added,
            "violations": self.violations,
        }


def _val(graph: Graph, subject: URIRef, predicate: URIRef, default=None):
    value = graph.value(subject, predicate)
    return default if value is None else value


def decode_registers(
    words: list[int],
    register_type: str = "uint16",
    word_order: str = "big",
    byte_order: str = "big",
    scale_factor: float = 1.0,
    offset: float = 0.0,
) -> float:
    if register_type not in REGISTER_TYPES:
        raise ValueError(f"unsupported register type '{register_type}'")

    count, fmt = REGISTER_TYPES[register_type]
    if len(words) < count:
        raise ValueError(f"{register_type} needs {count} words, got {len(words)}")

    selected = list(words[:count])
    if word_order == "little":
        selected.reverse()

    endian = ">" if byte_order == "big" else "<"
    raw = b"".join(struct.pack(f"{endian}H", w & 0xFFFF) for w in selected)
    value = struct.unpack(f"{endian}{fmt}", raw)[0]
    return float(value) * scale_factor + offset


def encode_value(
    value: float,
    register_type: str = "uint16",
    word_order: str = "big",
    byte_order: str = "big",
    scale_factor: float = 1.0,
    offset: float = 0.0,
) -> list[int]:
    if register_type not in REGISTER_TYPES:
        raise ValueError(f"unsupported register type '{register_type}'")

    count, fmt = REGISTER_TYPES[register_type]
    raw_value = (value - offset) / scale_factor if scale_factor else 0.0
    if fmt not in ("f",):
        raw_value = int(round(raw_value))

    endian = ">" if byte_order == "big" else "<"
    packed = struct.pack(f"{endian}{fmt}", raw_value)
    words = [
        struct.unpack(f"{endian}H", packed[i : i + 2])[0]
        for i in range(0, len(packed), 2)
    ]
    if word_order == "little":
        words.reverse()
    return words[:count]


def validate_bindings(turtle: str) -> tuple[bool, list[str], Graph]:
    graph = Graph()
    try:
        graph.parse(data=turtle, format="turtle")
    except Exception as exc:
        return False, [f"turtle parse error: {exc}"], Graph()

    if not any(graph.subjects(RDF.type, SF.ProtocolBinding)):
        return False, ["fragment declares no sf:ProtocolBinding"], graph

    try:
        import pyshacl
    except ImportError:
        return True, [], graph

    shapes = Graph()
    shapes.parse(data=BINDING_SHAPE_TTL, format="turtle")
    conforms, results, _ = pyshacl.validate(
        graph,
        shacl_graph=shapes,
        inference="none",
        abort_on_first=False,
        advanced=True,
    )
    if conforms:
        return True, [], graph

    SH = Namespace("http://www.w3.org/ns/shacl#")
    messages = [
        str(m)
        for node in results.subjects(RDF.type, SH.ValidationResult)
        for m in results.objects(node, SH.resultMessage)
    ]
    return False, messages or ["binding validation failed"], graph


def parse_bindings(graph: Graph) -> list[ProtocolBinding]:
    bindings = []
    for subject in graph.subjects(RDF.type, SF.ProtocolBinding):
        prop = _val(graph, subject, SF.bindsProperty)
        protocol = str(_val(graph, subject, SF.transportProtocol, "mqtt"))
        binding = ProtocolBinding(
            binding_id=_local(subject),
            device_id=str(_val(graph, subject, SF.deviceId, "")),
            property_name=_local(prop) if prop else "",
            protocol=protocol,
            subsystem=_local(_val(graph, subject, SF.belongsToSubsystem, "")) or "",
            unit=str(_val(graph, subject, SF.hasUnit, "")),
            poll_interval_ms=int(_val(graph, subject, SF.pollIntervalMs, 2000)),
            scale_factor=float(_val(graph, subject, SF.scaleFactor, 1.0)),
            offset=float(_val(graph, subject, SF.valueOffset, 0.0)),
            register_base=int(_val(graph, subject, SF.registerBase, 0)),
            register_count=int(_val(graph, subject, SF.registerCount, 1)),
            register_type=str(_val(graph, subject, SF.registerType, "uint16")),
            function_code=int(
                _val(graph, subject, SF.functionCode, DEFAULT_FUNCTION_CODE)
            ),
            word_order=str(_val(graph, subject, SF.wordOrder, "big")),
            byte_order=str(_val(graph, subject, SF.byteOrder, "big")),
            slave_id=int(_val(graph, subject, SF.slaveId, 1)),
            node_id=str(_val(graph, subject, SF.nodeId, "")),
            namespace_index=int(_val(graph, subject, SF.namespaceIndex, 2)),
            topic=str(_val(graph, subject, SF.mqttTopic, "")),
            qos=int(_val(graph, subject, SF.mqttQos, 1)),
            path=str(_val(graph, subject, SF.restPath, "")),
            method=str(_val(graph, subject, SF.restMethod, "POST")),
            device_aliases=sorted(
                str(a) for a in graph.objects(subject, SF.deviceAlias)
            ),
        )
        address = _val(graph, subject, SF.registerAddress)
        binding.register_address = int(address) if address is not None else None
        bindings.append(binding)
    bindings.sort(key=lambda b: (b.device_id, b.property_name))
    return bindings


class BindingRegistry:
    def __init__(self) -> None:
        self._graph = Graph()
        self._bindings: dict[str, ProtocolBinding] = {}

    def reset(self) -> None:
        self._graph = Graph()
        self._bindings.clear()

    def load_turtle(self, turtle: str) -> BindingLoadResult:
        accepted, violations, graph = validate_bindings(turtle)
        if not accepted:
            return BindingLoadResult(False, [], violations)

        self._graph += graph
        added = []
        for binding in parse_bindings(graph):
            self._bindings[binding.binding_id] = binding
            added.append(binding.binding_id)
        logger.info("protocol bindings loaded: %s", added)
        return BindingLoadResult(True, added, [])

    def all(self) -> list[ProtocolBinding]:
        return sorted(
            self._bindings.values(), key=lambda b: (b.device_id, b.property_name)
        )

    def get(self, binding_id: str) -> Optional[ProtocolBinding]:
        return self._bindings.get(binding_id)

    def for_protocol(self, protocol: str) -> list[ProtocolBinding]:
        return [b for b in self.all() if b.protocol == protocol]

    def for_device(self, device_id: str) -> list[ProtocolBinding]:
        resolved = self.resolve_device_id(device_id) or device_id
        return [b for b in self.all() if b.device_id == resolved]

    def devices(self) -> list[str]:
        return sorted({b.device_id for b in self._bindings.values()})

    def resolve_device_id(self, candidate: Any) -> Optional[str]:
        for binding in self.all():
            if binding.matches_device(candidate):
                return binding.device_id
        return None

    def aliases(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for binding in self.all():
            for alias in binding.device_aliases:
                out[str(alias)] = binding.device_id
        return out

    def graph(self) -> Graph:
        return self._graph

    def __len__(self) -> int:
        return len(self._bindings)


def generate_modbus_adapter(bindings: list[ProtocolBinding]) -> str:
    rows = []
    for b in bindings:
        rows.append(
            "    {"
            f'"device_id": "{b.device_id}", '
            f'"property_name": "{b.property_name}", '
            f'"canonical_subsystem": "{b.canonical_subsystem}", '
            f'"address": {b.register_address}, '
            f'"register_base": {b.register_base}, '
            f'"wire_address": {b.wire_address}, '
            f'"function_code": {b.function_code}, '
            f'"count": {b.register_count}, '
            f'"register_type": "{b.register_type}", '
            f'"word_order": "{b.word_order}", '
            f'"byte_order": "{b.byte_order}", '
            f'"scale_factor": {b.scale_factor}, '
            f'"offset": {b.offset}, '
            f'"slave_id": {b.slave_id}, '
            f'"poll_interval_ms": {b.poll_interval_ms}'
            "},"
        )
    table = "\n".join(rows)
    return f'''from semantic_layer.protocol_binding import decode_registers

REGISTER_MAP = [
{table}
]


def poll_groups():
    groups = {{}}
    for entry in REGISTER_MAP:
        key = (entry["slave_id"], entry["poll_interval_ms"])
        groups.setdefault(key, []).append(entry)
    return groups


def read_plan():
    groups = {{}}
    for entry in REGISTER_MAP:
        key = (
            entry["slave_id"],
            entry["function_code"],
            entry["poll_interval_ms"],
        )
        groups.setdefault(key, []).append(entry)

    plan = []
    for key in sorted(groups):
        slave_id, function_code, poll_interval_ms = key
        entries = sorted(groups[key], key=lambda e: e["wire_address"])
        start = min(e["wire_address"] for e in entries)
        end = max(e["wire_address"] + e["count"] for e in entries)
        plan.append(
            {{
                "slave_id": slave_id,
                "function_code": function_code,
                "poll_interval_ms": poll_interval_ms,
                "start_address": start,
                "count": end - start,
                "entries": entries,
            }}
        )
    return plan


def decode_entry(entry, words):
    return decode_registers(
        words,
        register_type=entry["register_type"],
        word_order=entry["word_order"],
        byte_order=entry["byte_order"],
        scale_factor=entry["scale_factor"],
        offset=entry["offset"],
    )


def build_message(entry, words, unit=""):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["canonical_subsystem"],
        "protocol": "modbus",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": decode_entry(entry, words),
                "unit": unit,
            }}
        ],
    }}
'''


def generate_opcua_adapter(bindings: list[ProtocolBinding]) -> str:
    rows = []
    for b in bindings:
        rows.append(
            "    {"
            f'"device_id": "{b.device_id}", '
            f'"property_name": "{b.property_name}", '
            f'"canonical_subsystem": "{b.canonical_subsystem}", '
            f'"node_id": "ns={b.namespace_index};s={b.node_id}", '
            f'"scale_factor": {b.scale_factor}, '
            f'"offset": {b.offset}, '
            f'"poll_interval_ms": {b.poll_interval_ms}'
            "},"
        )
    table = "\n".join(rows)
    return f'''NODE_MAP = [
{table}
]


def node_ids():
    return [entry["node_id"] for entry in NODE_MAP]


def entry_for_node(node_id):
    for entry in NODE_MAP:
        if entry["node_id"] == node_id:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value, unit=""):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["canonical_subsystem"],
        "protocol": "opcua",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": unit,
            }}
        ],
    }}
'''


def generate_mqtt_adapter(bindings: list[ProtocolBinding]) -> str:
    rows = []
    for b in bindings:
        subsystem = b.canonical_subsystem
        topic = b.topic or f"factory/{subsystem}/sensors/{b.device_id}/{b.property_name}"
        rows.append(
            "    {"
            f'"device_id": "{b.device_id}", '
            f'"property_name": "{b.property_name}", '
            f'"canonical_subsystem": "{subsystem}", '
            f'"topic": "{topic}", '
            f'"qos": {b.qos}, '
            f'"scale_factor": {b.scale_factor}, '
            f'"offset": {b.offset}'
            "},"
        )
    table = "\n".join(rows)
    return f'''TOPIC_MAP = [
{table}
]


def subscriptions():
    return [(entry["topic"], entry["qos"]) for entry in TOPIC_MAP]


def entry_for_topic(topic):
    for entry in TOPIC_MAP:
        if entry["topic"] == topic:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value, unit=""):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["canonical_subsystem"],
        "protocol": "mqtt",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": unit,
            }}
        ],
    }}
'''


def generate_rest_adapter(bindings: list[ProtocolBinding]) -> str:
    rows = []
    for b in bindings:
        rows.append(
            "    {"
            f'"device_id": "{b.device_id}", '
            f'"property_name": "{b.property_name}", '
            f'"canonical_subsystem": "{b.canonical_subsystem}", '
            f'"path": "{b.path or "/adapter/rest/ingest"}", '
            f'"method": "{b.method}", '
            f'"scale_factor": {b.scale_factor}, '
            f'"offset": {b.offset}'
            "},"
        )
    table = "\n".join(rows)
    return f'''ROUTE_MAP = [
{table}
]


def routes():
    return sorted({{(entry["path"], entry["method"]) for entry in ROUTE_MAP}})


def entries_for_path(path):
    return [entry for entry in ROUTE_MAP if entry["path"] == path]


def entry_for_device(device_id, property_name=None):
    for entry in ROUTE_MAP:
        if entry["device_id"] != device_id:
            continue
        if property_name is None or entry["property_name"] == property_name:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value, unit=""):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["canonical_subsystem"],
        "protocol": "rest",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": unit,
            }}
        ],
    }}
'''


GENERATORS = {
    "modbus": generate_modbus_adapter,
    "opcua": generate_opcua_adapter,
    "mqtt": generate_mqtt_adapter,
    "rest": generate_rest_adapter,
}


def generate_adapter(protocol: str, bindings: list[ProtocolBinding]) -> str:
    if protocol not in GENERATORS:
        raise ValueError(f"no generator for protocol '{protocol}'")
    selected = [b for b in bindings if b.protocol == protocol]
    if not selected:
        raise ValueError(f"no bindings declared for protocol '{protocol}'")
    return GENERATORS[protocol](selected)


def generate_all(registry: BindingRegistry) -> dict[str, str]:
    out = {}
    for protocol in GENERATORS:
        selected = registry.for_protocol(protocol)
        if selected:
            out[protocol] = GENERATORS[protocol](selected)
    return out


registry = BindingRegistry()
