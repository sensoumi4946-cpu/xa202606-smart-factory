from __future__ import annotations

import logging
import io
import tokenize
import pprint
import struct
from dataclasses import dataclass, field
from typing import Any, Optional

from rdflib import Graph, Namespace, RDF, URIRef

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")

SUPPORTED_PROTOCOLS = ("modbus", "opcua", "mqtt", "rest")

WORD_ORDERS = ("big", "little")
BYTE_ORDERS = ("big", "little")

CANONICAL_SUBSYSTEMS = ("temp_humidity", "lighting", "gas", "agv", "counting")

REGISTER_BASES = (0, 1, 30001, 40001)

FUNCTION_CODES = {
    1: "read_coils",
    2: "read_discrete_inputs",
    3: "read_holding_registers",
    4: "read_input_registers",
}


def canonical_subsystem(name: str) -> str:
    token = (name or "").strip().lower()
    if token.endswith("_subsystem"):
        token = token[: -len("_subsystem")]
    aliases = {
        "temperature_humidity": "temp_humidity",
        "temphumidity": "temp_humidity",
        "light": "lighting",
        "people_counting": "counting",
        "agv_guard": "agv",
    }
    return aliases.get(token, token)


REGISTER_TYPES = {
    "int16": (1, "h"),
    "uint16": (1, "H"),
    "int32": (2, "i"),
    "uint32": (2, "I"),
    "float32": (2, "f"),
}

BINDING_SHAPE_TTL = """
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
        sh:path sf:registerType ;
        sh:maxCount 1 ;
        sh:in ( "int16" "uint16" "int32" "uint32" "float32" ) ;
        sh:message "registerType must be int16, uint16, int32, uint32 or float32" ;
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
    ] ;
    sh:property [
        sh:path sf:registerBase ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:in ( 0 1 30001 40001 ) ;
        sh:message "registerBase must be 0, 1, 30001 or 40001" ;
    ] ;
    sh:property [
        sh:path sf:functionCode ;
        sh:maxCount 1 ; sh:datatype xsd:integer ;
        sh:in ( 1 2 3 4 ) ;
        sh:message "functionCode must be 1, 2, 3 or 4" ;
    ] .

sf:ModbusBindingShape a sh:NodeShape ;
    sh:targetClass sf:ProtocolBinding ;
    sh:sparql [
        sh:message "modbus binding must declare sf:registerAddress" ;
        sh:select \"\"\"
            SELECT $this WHERE {
                $this <http://example.org/smart-factory#transportProtocol> "modbus" .
                FILTER NOT EXISTS {
                    $this <http://example.org/smart-factory#registerAddress> ?a .
                }
            }
        \"\"\" ;
    ] .

sf:OpcuaBindingShape a sh:NodeShape ;
    sh:targetClass sf:ProtocolBinding ;
    sh:sparql [
        sh:message "opcua binding must declare sf:nodeId" ;
        sh:select \"\"\"
            SELECT $this WHERE {
                $this <http://example.org/smart-factory#transportProtocol> "opcua" .
                FILTER NOT EXISTS {
                    $this <http://example.org/smart-factory#nodeId> ?n .
                }
            }
        \"\"\" ;
    ] .
"""


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
    register_count: int = 1
    register_type: str = "uint16"
    word_order: str = "big"
    byte_order: str = "big"
    register_base: int = 0
    function_code: int = 3
    slave_id: int = 1
    device_aliases: list[str] = field(default_factory=list)
    node_id: str = ""
    namespace_index: int = 2
    topic: str = ""
    qos: int = 1
    path: str = ""
    method: str = "POST"

    @property
    def wire_address(self) -> Optional[int]:
        if self.register_address is None:
            return None
        return self.register_address - self.register_base

    @property
    def canonical_subsystem(self) -> str:
        return canonical_subsystem(self.subsystem)

    def matches_device(self, device_id: str) -> bool:
        return device_id == self.device_id or device_id in self.device_aliases

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "device_id": self.device_id,
            "property_name": self.property_name,
            "protocol": self.protocol,
            "subsystem": self.subsystem,
            "unit": self.unit,
            "poll_interval_ms": self.poll_interval_ms,
            "scale_factor": self.scale_factor,
            "offset": self.offset,
            "register_address": self.register_address,
            "register_count": self.register_count,
            "register_type": self.register_type,
            "word_order": self.word_order,
            "byte_order": self.byte_order,
            "register_base": self.register_base,
            "function_code": self.function_code,
            "wire_address": self.wire_address,
            "slave_id": self.slave_id,
            "device_aliases": list(self.device_aliases),
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
    messages: list[str] = []
    if isinstance(results, Graph):
        for node in results.subjects(RDF.type, SH.ValidationResult):
            for m in results.objects(node, SH.resultMessage):
                messages.append(str(m))
    elif results is not None:
        messages.append(str(results))
    return False, messages or ["binding validation failed"], graph


def parse_bindings(graph: Graph) -> list[ProtocolBinding]:
    bindings = []
    for subject in graph.subjects(RDF.type, SF.ProtocolBinding):
        if not isinstance(subject, URIRef):
            continue
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
            register_count=int(_val(graph, subject, SF.registerCount, 1)),
            register_type=str(_val(graph, subject, SF.registerType, "uint16")),
            word_order=str(_val(graph, subject, SF.wordOrder, "big")),
            byte_order=str(_val(graph, subject, SF.byteOrder, "big")),
            register_base=int(_val(graph, subject, SF.registerBase, 0)),
            function_code=int(_val(graph, subject, SF.functionCode, 3)),
            slave_id=int(_val(graph, subject, SF.slaveId, 1)),
            device_aliases=sorted(
                str(a) for a in graph.objects(subject, SF.deviceAlias)
            ),
            node_id=str(_val(graph, subject, SF.nodeId, "")),
            namespace_index=int(_val(graph, subject, SF.namespaceIndex, 2)),
            topic=str(_val(graph, subject, SF.mqttTopic, "")),
            qos=int(_val(graph, subject, SF.mqttQos, 1)),
            path=str(_val(graph, subject, SF.restPath, "")),
            method=str(_val(graph, subject, SF.restMethod, "POST")),
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

        parsed = parse_bindings(graph)
        duplicate_ids = sorted(
            binding.binding_id
            for binding in parsed
            if binding.binding_id in self._bindings
        )
        if duplicate_ids:
            return BindingLoadResult(
                False,
                [],
                [f"duplicate binding id: {binding_id}" for binding_id in duplicate_ids],
            )

        collisions = _modbus_collisions([*self._bindings.values(), *parsed])
        if collisions:
            return BindingLoadResult(False, [], collisions)

        self._graph += graph
        added = []
        for binding in parsed:
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
        return [b for b in self.all() if b.matches_device(device_id)]

    def resolve_device_id(self, device_id: str) -> str:
        for binding in self._bindings.values():
            if device_id in binding.device_aliases:
                return binding.device_id
        return device_id

    def aliases(self) -> dict[str, str]:
        return {
            alias: b.device_id
            for b in self._bindings.values()
            for alias in b.device_aliases
        }

    def devices(self) -> list[str]:
        return sorted({b.device_id for b in self._bindings.values()})

    def __len__(self) -> int:
        return len(self._bindings)


def _modbus_collisions(bindings: list[ProtocolBinding]) -> list[str]:
    occupied: dict[tuple[int, int, int], str] = {}
    violations: list[str] = []
    for binding in sorted(bindings, key=lambda item: item.binding_id):
        if binding.protocol != "modbus" or binding.wire_address is None:
            continue
        for address in range(
            binding.wire_address, binding.wire_address + binding.register_count
        ):
            key = (binding.slave_id, binding.function_code, address)
            previous = occupied.get(key)
            if previous is not None:
                violations.append(
                    "Modbus address collision: "
                    f"slave={binding.slave_id}, function={binding.function_code}, "
                    f"wire_address={address} used by {previous} and {binding.binding_id}"
                )
            else:
                occupied[key] = binding.binding_id
    return violations


def _literal_table(rows: list[dict[str, Any]]) -> str:
    return pprint.pformat(rows, width=100, sort_dicts=False)


def generate_modbus_adapter(bindings: list[ProtocolBinding]) -> str:
    rows: list[dict[str, Any]] = []
    for b in bindings:
        rows.append(
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": b.canonical_subsystem,
                "unit": b.unit,
                "address": b.wire_address,
                "declared_address": b.register_address,
                "register_base": b.register_base,
                "function_code": b.function_code,
                "count": b.register_count,
                "register_type": b.register_type,
                "word_order": b.word_order,
                "byte_order": b.byte_order,
                "scale_factor": b.scale_factor,
                "offset": b.offset,
                "slave_id": b.slave_id,
                "poll_interval_ms": b.poll_interval_ms,
            }
        )
    table = _literal_table(rows)
    return f"""from semantic_layer.protocol_binding import decode_registers

REGISTER_MAP = {table}


FUNCTION_CODE_CALLS = {{
    1: "read_coils",
    2: "read_discrete_inputs",
    3: "read_holding_registers",
    4: "read_input_registers",
}}


def poll_groups():
    groups = {{}}
    for entry in REGISTER_MAP:
        key = (entry["slave_id"], entry["function_code"], entry["poll_interval_ms"])
        groups.setdefault(key, []).append(entry)
    return groups


def read_plan():
    plan = []
    for (slave_id, function_code, interval), entries in poll_groups().items():
        addresses = [e["address"] for e in entries]
        start = min(addresses)
        span = max(a + e["count"] for a, e in zip(addresses, entries)) - start
        plan.append(
            {{
                "slave_id": slave_id,
                "call": FUNCTION_CODE_CALLS[function_code],
                "address": start,
                "count": span,
                "poll_interval_ms": interval,
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


def build_message(entry, words):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "modbus",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": decode_entry(entry, words),
                "unit": entry["unit"],
            }}
        ],
    }}
"""


def generate_opcua_adapter(bindings: list[ProtocolBinding]) -> str:
    rows: list[dict[str, Any]] = []
    for b in bindings:
        rows.append(
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": b.canonical_subsystem,
                "unit": b.unit,
                "node_id": f"ns={b.namespace_index};s={b.node_id}",
                "scale_factor": b.scale_factor,
                "offset": b.offset,
                "poll_interval_ms": b.poll_interval_ms,
            }
        )
    table = _literal_table(rows)
    return f"""NODE_MAP = {table}


def node_ids():
    return [entry["node_id"] for entry in NODE_MAP]


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "opcua",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": entry["unit"],
            }}
        ],
    }}
"""


def generate_mqtt_adapter(bindings: list[ProtocolBinding]) -> str:
    rows: list[dict[str, Any]] = []
    for b in bindings:
        topic = (
            b.topic or f"factory/{b.subsystem}/sensors/{b.device_id}/{b.property_name}"
        )
        rows.append(
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": b.canonical_subsystem,
                "unit": b.unit,
                "topic": topic,
                "qos": b.qos,
                "scale_factor": b.scale_factor,
                "offset": b.offset,
            }
        )
    table = _literal_table(rows)
    return f"""TOPIC_MAP = {table}


def subscriptions():
    return [(entry["topic"], entry["qos"]) for entry in TOPIC_MAP]


def entry_for_topic(topic):
    for entry in TOPIC_MAP:
        if entry["topic"] == topic:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]
"""


def generate_rest_adapter(bindings: list[ProtocolBinding]) -> str:
    rows: list[dict[str, Any]] = []
    for b in bindings:
        path = b.path or "/adapter/rest/ingest"
        rows.append(
            {
                "device_id": b.device_id,
                "property_name": b.property_name,
                "subsystem": b.canonical_subsystem,
                "unit": b.unit,
                "path": path,
                "method": b.method,
                "scale_factor": b.scale_factor,
                "offset": b.offset,
                "poll_interval_ms": b.poll_interval_ms,
            }
        )
    table = _literal_table(rows)
    return f"""ROUTE_MAP = {table}


def routes():
    return sorted({{(entry["method"], entry["path"]) for entry in ROUTE_MAP}})


def entries_for_device(device_id):
    return [entry for entry in ROUTE_MAP if entry["device_id"] == device_id]


def entry_for(device_id, property_name):
    for entry in ROUTE_MAP:
        if entry["device_id"] == device_id and entry["property_name"] == property_name:
            return entry
    return None


def scale(entry, raw_value):
    return float(raw_value) * entry["scale_factor"] + entry["offset"]


def build_message(entry, raw_value):
    return {{
        "schema_version": "v1",
        "device_id": entry["device_id"],
        "subsystem": entry["subsystem"],
        "protocol": "rest",
        "measurements": [
            {{
                "type": entry["property_name"],
                "value": scale(entry, raw_value),
                "unit": entry["unit"],
            }}
        ],
    }}
"""


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
    for protocol, source in out.items():
        tokens = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type != tokenize.COMMENT]
        out[protocol] = tokenize.untokenize(tokens)
    return out


registry = BindingRegistry()