from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from backend import config

from analytics.decision_provenance import ledger
from semantic_layer.cross_factory import (
    FactorySite,
    coordinator,
    seed_demo_sites,
    site_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["federation"])


class SiteRegistration(BaseModel):
    site_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    sparql_endpoint: str = Field(..., min_length=1)
    ontology_namespace: str = "http://example.org/smart-factory#"
    alignment: dict[str, str] = Field(default_factory=dict)
    region: str = ""


class SeedRequest(BaseModel):
    local_sparql: str = config.FUSEKI_QUERY_URL
    partner_sparql: str = "http://localhost:3031/partner/sparql"


@router.post("/api/v1/federation/sites", status_code=status.HTTP_201_CREATED)
async def register_site(req: SiteRegistration) -> dict[str, Any]:
    site_registry.register(
        FactorySite(
            site_id=req.site_id,
            display_name=req.display_name,
            sparql_endpoint=req.sparql_endpoint,
            ontology_namespace=req.ontology_namespace,
            alignment=req.alignment,
            region=req.region,
        )
    )
    return {"site_id": req.site_id, "registered": True, "total_sites": len(site_registry)}


@router.post("/api/v1/federation/seed", status_code=status.HTTP_201_CREATED)
async def seed(req: SeedRequest) -> dict[str, Any]:
    seed_demo_sites(req.local_sparql, req.partner_sparql)
    return {"seeded": True, "total_sites": len(site_registry)}


@router.get("/api/v1/federation/sites")
async def list_sites() -> dict[str, Any]:
    items = [
        {
            "site_id": s.site_id,
            "display_name": s.display_name,
            "sparql_endpoint": s.sparql_endpoint,
            "ontology_namespace": s.ontology_namespace,
            "alignment": s.alignment,
            "region": s.region,
            "online": s.online,
        }
        for s in site_registry.all()
    ]
    return {"items": items, "total": len(items)}


@router.delete("/api/v1/federation/sites/{site_id}")
async def remove_site(site_id: str) -> dict[str, Any]:
    if site_registry.get(site_id) is None:
        raise HTTPException(status_code=404, detail="site not found")
    site_registry.unregister(site_id)
    return {"site_id": site_id, "removed": True}


@router.post("/api/v1/federation/sites/{site_id}/online")
async def set_online(site_id: str, online: bool = True) -> dict[str, Any]:
    if site_registry.get(site_id) is None:
        raise HTTPException(status_code=404, detail="site not found")
    site_registry.set_online(site_id, online)
    return {"site_id": site_id, "online": online}


@router.get("/api/v1/federation/query")
async def federated_query(
    property: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    sites: Optional[str] = None,
) -> dict[str, Any]:
    site_ids = [s.strip() for s in sites.split(",")] if sites else None
    result = await coordinator.query_property(property, limit, site_ids)
    return result.to_dict()


@router.get("/api/v1/federation/compare")
async def federated_compare(
    property: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    return await coordinator.compare_property(property, limit)


@router.get("/api/v1/decisions")
async def list_decisions(
    policy_name: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    items = [r.to_dict() for r in ledger.list(policy_name, severity, limit)]
    return {"items": items, "total": len(ledger)}


@router.get("/api/v1/decisions/{decision_id}")
async def decision_detail(decision_id: str) -> dict[str, Any]:
    record = ledger.get(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return record.to_dict()


@router.get("/api/v1/decisions/{decision_id}/verify")
async def verify_decision(decision_id: str) -> dict[str, Any]:
    from backend.security import command_audit

    record = ledger.get(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="decision not found")

    chain = command_audit.verify_chain()
    entries = (
        command_audit.query(command_id=record.command_id, limit=5)
        if record.command_id
        else []
    )
    return {
        "decision_id": decision_id,
        "fingerprint": record.fingerprint(),
        "audit_seq": record.audit_seq,
        "audit_hash": record.audit_hash,
        "audit_entries": entries,
        "chain_valid": chain["valid"],
        "chain_entries": chain["entries"],
        "chain_detail": chain,
    }
