from fastapi import APIRouter

from backend import config
from semantic_layer.cross_alert import check_fire_risk

router = APIRouter()

@router.get("/api/v1/semantic/fire-risk")
async def fire_risk():
    """Check whether a cross-device fire risk condition exists in the knowledge graph.
    """
    result = await check_fire_risk(config.FUSEKI_QUERY_URL)

    if result is None:
        return {"risk_detected": False}

    return {"risk_detected": True, **result}
