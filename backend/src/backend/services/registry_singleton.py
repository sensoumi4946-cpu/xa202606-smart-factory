

from semantic_layer.aas_live_sync import AASRegistry
from semantic_layer.semantic_provenance_audit import ProvenanceAuditLog

aas_registry = AASRegistry()

from pathlib import Path
from backend import config

Path(config.PROVENANCE_AUDIT_DB).parent.mkdir(parents=True, exist_ok=True)
provenance_audit = ProvenanceAuditLog(Path(config.PROVENANCE_AUDIT_DB))