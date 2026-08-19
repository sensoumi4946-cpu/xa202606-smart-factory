from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from rdflib import Graph, Namespace, RDF, URIRef
from rdflib.namespace import OWL, RDFS

logger = logging.getLogger(__name__)

SF = Namespace("http://example.org/smart-factory#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")

CHANGE_RENAME = "rename"
CHANGE_ADD = "add"
CHANGE_REMOVE = "remove"
CHANGE_RETYPE = "retype"
CHANGE_NARROW_RANGE = "narrow_range"
CHANGE_WIDEN_RANGE = "widen_range"
CHANGE_UNIT = "unit_change"

BREAKING = {CHANGE_REMOVE, CHANGE_RETYPE, CHANGE_UNIT, CHANGE_NARROW_RANGE}


@dataclass
class Change:
    kind: str
    property_name: str
    before: Optional[str] = None
    after: Optional[str] = None
    breaking: bool = False
    detail_zh: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "property_name": self.property_name,
            "before": self.before,
            "after": self.after,
            "breaking": self.breaking,
            "detail_zh": self.detail_zh,
        }


@dataclass
class MigrationPlan:
    from_version: str
    to_version: str
    changes: list[Change] = field(default_factory=list)
    alignment_axioms: str = ""
    compatible: bool = True
    blocked_reasons: list[str] = field(default_factory=list)
    generated_at: str = ""

    @property
    def breaking_changes(self) -> list[Change]:
        return [c for c in self.changes if c.breaking]

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "changes": [c.to_dict() for c in self.changes],
            "alignment_axioms": self.alignment_axioms,
            "compatible": self.compatible,
            "blocked_reasons": self.blocked_reasons,
            "generated_at": self.generated_at,
            "breaking_count": len(self.breaking_changes),
        }

    def summary_zh(self) -> str:
        if self.compatible:
            return (
                f"从 {self.from_version} 迁移到 {self.to_version} 兼容："
                f"共 {len(self.changes)} 处变更，已生成 owl:equivalentProperty "
                f"对齐公理，历史数据无需改写即可继续查询。"
            )
        return (
            f"从 {self.from_version} 迁移到 {self.to_version} 被阻断："
            f"存在 {len(self.breaking_changes)} 处破坏性变更，"
            f"历史数据将无法按新本体查询。"
        )


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


def _float(graph: Graph, subject: Any, predicate: Any) -> Optional[float]:
    value = graph.value(subject, predicate)
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


@dataclass
class PropertySnapshot:
    name: str
    uri: str
    unit: str
    min_value: Optional[float]
    max_value: Optional[float]
    labels: dict[str, str]


def snapshot(graph: Graph) -> dict[str, PropertySnapshot]:
    out: dict[str, PropertySnapshot] = {}
    for subject in graph.subjects(RDF.type, SOSA.ObservableProperty):
        name = _local(subject)
        labels = {
            (getattr(lit, "language", None) or "en"): str(lit)
            for lit in graph.objects(subject, RDFS.label)
        }
        out[name] = PropertySnapshot(
            name=name,
            uri=str(subject),
            unit=str(graph.value(subject, SF.hasUnit) or ""),
            min_value=_float(graph, subject, SF.minValue),
            max_value=_float(graph, subject, SF.maxValue),
            labels=labels,
        )
    return out


def _rename_candidates(
    removed: dict[str, PropertySnapshot], added: dict[str, PropertySnapshot]
) -> list[tuple[str, str]]:
    """Match a dropped property to a new one that means the same thing.

    A rename is only a rename if the unit and range are unchanged; otherwise
    it is a removal plus an unrelated addition, and history cannot follow it.
    """
    pairs = []
    for old_name, old in removed.items():
        for new_name, new in added.items():
            same_unit = old.unit == new.unit
            same_range = (
                old.min_value == new.min_value and old.max_value == new.max_value
            )
            shared_label = bool(
                {v for v in old.labels.values()} & {v for v in new.labels.values()}
            )
            if same_unit and same_range and (shared_label or old_name in new_name or new_name in old_name):
                pairs.append((old_name, new_name))
                break
    return pairs


def diff(old_graph: Graph, new_graph: Graph) -> list[Change]:
    before = snapshot(old_graph)
    after = snapshot(new_graph)

    removed = {k: v for k, v in before.items() if k not in after}
    added = {k: v for k, v in after.items() if k not in before}
    renames = _rename_candidates(removed, added)
    renamed_old = {old for old, _ in renames}
    renamed_new = {new for _, new in renames}

    changes: list[Change] = []

    for old_name, new_name in renames:
        changes.append(
            Change(
                kind=CHANGE_RENAME,
                property_name=new_name,
                before=old_name,
                after=new_name,
                breaking=False,
                detail_zh=f"属性 {old_name} 更名为 {new_name}，单位与量程不变，可用对齐公理兼容",
            )
        )

    for name in sorted(set(removed) - renamed_old):
        changes.append(
            Change(
                kind=CHANGE_REMOVE,
                property_name=name,
                before=name,
                breaking=True,
                detail_zh=f"属性 {name} 被删除，历史观测将无法按新本体解释",
            )
        )

    for name in sorted(set(added) - renamed_new):
        changes.append(
            Change(
                kind=CHANGE_ADD,
                property_name=name,
                after=name,
                breaking=False,
                detail_zh=f"新增属性 {name}，不影响历史数据",
            )
        )

    for name in sorted(set(before) & set(after)):
        old, new = before[name], after[name]

        if old.unit != new.unit:
            changes.append(
                Change(
                    kind=CHANGE_UNIT,
                    property_name=name,
                    before=old.unit,
                    after=new.unit,
                    breaking=True,
                    detail_zh=f"{name} 单位由 {old.unit} 改为 {new.unit}，历史数值含义改变",
                )
            )

        old_lo, old_hi = old.min_value, old.max_value
        new_lo, new_hi = new.min_value, new.max_value
        if (
            old_lo is not None
            and old_hi is not None
            and new_lo is not None
            and new_hi is not None
        ):
            narrowed = new_lo > old_lo or new_hi < old_hi
            widened = new_lo < old_lo or new_hi > old_hi
            if narrowed:
                changes.append(
                    Change(
                        kind=CHANGE_NARROW_RANGE,
                        property_name=name,
                        before=f"[{old_lo}, {old_hi}]",
                        after=f"[{new_lo}, {new_hi}]",
                        breaking=True,
                        detail_zh=f"{name} 量程收窄，部分历史数据会变成非法值",
                    )
                )
            elif widened:
                changes.append(
                    Change(
                        kind=CHANGE_WIDEN_RANGE,
                        property_name=name,
                        before=f"[{old_lo}, {old_hi}]",
                        after=f"[{new_lo}, {new_hi}]",
                        breaking=False,
                        detail_zh=f"{name} 量程放宽，历史数据仍然合法",
                    )
                )

    return changes


def alignment_axioms(changes: list[Change], old_graph: Graph, new_graph: Graph) -> str:
    """Emit owl:equivalentProperty so v1 triples answer v2 queries."""
    renames = [c for c in changes if c.kind == CHANGE_RENAME]
    if not renames:
        return ""

    before = snapshot(old_graph)
    after = snapshot(new_graph)

    lines = [
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "",
    ]
    for change in renames:
        old = before.get(str(change.before))
        new = after.get(str(change.after))
        if old is None or new is None:
            continue
        lines.append(f"<{old.uri}> owl:equivalentProperty <{new.uri}> ;")
        lines.append(f'    rdfs:comment "renamed in migration"@en .')
        lines.append("")
    return "\n".join(lines)


def plan_migration(
    old_turtle: str,
    new_turtle: str,
    from_version: str = "v1",
    to_version: str = "v2",
    allow_breaking: bool = False,
) -> MigrationPlan:
    old_graph = Graph()
    new_graph = Graph()
    old_graph.parse(data=old_turtle, format="turtle")
    new_graph.parse(data=new_turtle, format="turtle")

    changes = diff(old_graph, new_graph)
    breaking = [c for c in changes if c.breaking]

    plan = MigrationPlan(
        from_version=from_version,
        to_version=to_version,
        changes=changes,
        alignment_axioms=alignment_axioms(changes, old_graph, new_graph),
        compatible=allow_breaking or not breaking,
        blocked_reasons=[c.detail_zh for c in breaking] if not allow_breaking else [],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    if plan.compatible:
        logger.info(
            "migration %s -> %s accepted: %d changes",
            from_version,
            to_version,
            len(changes),
        )
    else:
        logger.error(
            "migration %s -> %s blocked: %d breaking changes",
            from_version,
            to_version,
            len(breaking),
        )
    return plan


def rewrite_query(sparql: str, changes: list[Change]) -> str:
    """Rewrite a v1 query so it runs against a v2 ontology."""
    rewritten = sparql
    for change in changes:
        if change.kind != CHANGE_RENAME or not change.before or not change.after:
            continue
        old_camel = "".join(p.capitalize() for p in change.before.split("_"))
        new_camel = "".join(p.capitalize() for p in change.after.split("_"))
        rewritten = rewritten.replace(f"sf:measures{old_camel}", f"sf:measures{new_camel}")
        rewritten = rewritten.replace(f'"{change.before}"', f'"{change.after}"')
    return rewritten


def render(plan: MigrationPlan) -> str:
    lines = [
        "",
        f"本体迁移  {plan.from_version} -> {plan.to_version}",
        "-" * 66,
    ]
    for change in plan.changes:
        mark = "BREAK" if change.breaking else "  ok "
        lines.append(f"  [{mark}] {change.kind:<14} {change.detail_zh}")
    lines += ["-" * 66, f"  {plan.summary_zh()}", ""]
    if plan.alignment_axioms:
        lines += ["  生成的对齐公理:", ""]
        lines += [f"    {ln}" for ln in plan.alignment_axioms.splitlines() if ln.strip()]
        lines.append("")
    return "\n".join(lines)


def to_json(plan: MigrationPlan) -> str:
    return json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)