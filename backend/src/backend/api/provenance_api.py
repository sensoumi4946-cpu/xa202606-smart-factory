from fastapi import APIRouter, Query
from backend import config
from semantic_layer.semantic_provenance_audit import ProvenanceAuditLog

router = APIRouter()
_audit = ProvenanceAuditLog()

@router.get("/api/v1/semantic/provenance/completeness")
async def provenance_completeness(window_hours: int = Query(24, ge=1, le=168)):
    report = _audit.completeness_ratio(window_hours=window_hours)
    return report.to_dict()

@router.get("/api/v1/semantic/provenance/pending")
async def provenance_pending():
    return {"pending": _audit.pending_retries(limit=100)}