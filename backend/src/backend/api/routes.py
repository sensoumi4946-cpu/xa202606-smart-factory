from fastapi import APIRouter

from backend.api.aas import router as aas_router
from backend.api.alerts import router as alerts_router
from backend.api.analytics_api import router as analytics_router
from backend.api.assistant_api import router as assistant_router
from backend.api.control import router as control_router
from backend.api.federated import router as federated_router
from backend.api.federation_api import router as federation_router
from backend.api.fire_risk import router as fire_risk_router
from backend.api.health_check import router as health_router
from backend.api.history import router as history_router
from backend.api.ingest import router as ingest_router
from backend.api.innovation_api import router as innovation_router
from backend.api.latest import router as latest_router
from backend.api.ontology_api import router as ontology_router
from backend.api.ops import router as ops_router
from backend.api.prediction import router as prediction_router
from backend.api.provenance_api import router as provenance_router
from backend.api.query import router as query_router
from backend.api.security_api import router as security_router
from backend.api.semantic import router as semantic_router
from backend.api.semantic_gate_status import router as gate_status_router
from backend.api.semantic_query import router as semantic_query_router

INGEST = (ingest_router,)

SEMANTIC = (
    semantic_router,
    semantic_query_router,
    ontology_router,
    innovation_router,
    gate_status_router,
    provenance_router,
)

DATA = (query_router, latest_router, history_router, aas_router)

ANALYTICS = (
    alerts_router,
    analytics_router,
    prediction_router,
    fire_risk_router,
    control_router,
)

FEDERATION = (federated_router, federation_router)

PLATFORM = (health_router, ops_router, security_router, assistant_router)

GROUPS = {
    "ingest": INGEST,
    "semantic": SEMANTIC,
    "data": DATA,
    "analytics": ANALYTICS,
    "federation": FEDERATION,
    "platform": PLATFORM,
}

api_router = APIRouter()

for _group in GROUPS.values():
    for _router in _group:
        api_router.include_router(_router)