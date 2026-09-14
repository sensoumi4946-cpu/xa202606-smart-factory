# Backend

The backend is the orchestration and trust boundary of XA-202606.

## Responsibilities

- FastAPI HTTP API
- API-key authentication
- device alias resolution and binding checks
- SHACL gate orchestration
- SQLite persistence
- synchronous analytics dispatch
- prediction/hazard/control APIs
- backend-side command signing
- command dispatch and ACK handling
- audit-chain persistence
- health/readiness endpoints
- semantic query proxy and degraded behavior

## Ingest path

```text
adapter
  ↓
POST /ingest/api/v1/data
  ↓
API key / contract / alias / binding checks
  ↓
SHACL
  ├─ reject → 422 + provenance/reason
  └─ pass
       ↓
     SQLite
       ↓
     analytics
       ↓
     optional background semantic persistence
```

Fuseki persistence is not allowed to roll back valid core business ingestion.

## Important endpoints

- `POST /ingest/api/v1/data`
- `GET /api/v1/latest`
- `GET /api/v1/history`
- `GET /api/v1/predictions`
- `GET /api/v1/alerts`
- `GET /api/v1/semantic`
- semantic query/gate-status routes
- `POST /api/v1/control`
- `/health`, `/health/live`, `/health/ready`

Protected APIs use `X-API-Key`.

## Control security

The frontend submits a `ControlRequest`; it does not create HMAC signatures.

```text
ControlRequest
   ↓
backend auth
   ↓
persist command
   ↓
create signed command envelope
   ↓
dispatcher
   ↓
device/simulator
   ↓
ACK
   ↓
status + command_audit
```

Set:

```bash
API_KEY=...
COMMAND_SIGNING_KEY=...
```

Do not commit real secrets.

## Run

From repository root:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Test

```bash
python -m pytest backend/tests -q
```