# Shared module-level singletons

from semantic_layer.aas_live_sync import AASRegistry
from semantic_layer.semantic_provenance_audit import ProvenanceAuditLog

aas_registry = AASRegistry()

provenance_audit = ProvenanceAuditLog()