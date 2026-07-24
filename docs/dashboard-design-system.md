# Dashboard Design System (v1)

Style guide for the XA-202606 Smart Factory dashboard. All values live in
`dashboard/src/styles/tokens.css` components must reference tokens, never
hard coded colors.

## Design concept

The dashboard reads as a **safety control room**, top to bottom:

1. **SystemPulse** one glance answers "is the factory safe?"
   (NORMAL / WARNING / CRITICAL, computed from active alerts)
2. **CrossAlertBanner** appears only during a cross subsystem correlation
   (e.g. fire risk), showing the causal chain: two sensors → one event
3. **Sensor grid** live per device detail; click any card for history
4. **Knowledge graph + alert feed** the semantic structure (ontology) and
   the event log side by side

The signature visual element is the **hazard stripe**: the brand mark in the
top bar and the left edge of SystemPulse, which animates during a critical
state.

## Color

Palette is derived from industrial safety signage, not generic dark UI
defaults. Violet is reserved exclusively for semantic layer (ontology)
entities so the knowledge graph reads as its own domain.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#111417` | App background (neutral graphite) |
| `--surface` | `#191e24` | Panels/cards |
| `--surface-2` | `#1f262e` | Inputs, badges, raised chips |
| `--line` / `--line-strong` | `#2a313a` / `#3a434e` | Borders |
| `--text` / `--text-dim` / `--text-faint` | `#e8eaed` / `#9aa3af` / `#6b7480` | Text hierarchy |
| `--ok` | `#4cc38a` | Normal state, online lamps |
| `--warn` | `#f5a524` | Caution + **brand accent** (safety amber) |
| `--danger` | `#f04444` | Critical alerts, offline |
| `--semantic` | `#8b8cf6` | Ontology / knowledge graph entities only |
| `--data-1/2/3` | `#56b4e9` `#e69f00` `#4cc38a` | Chart series (colorblind safe) |

Rules:
- Red and amber are **meaningful** never use them decoratively.
- Each `--ok/--warn/--danger` has a matching `*-bg` translucent fill for row
  backgrounds.

## Typography

No webfont downloads (the platform must run offline on UOS/openEuler);
stacks resolve to fonts already present on domestic systems.

| Token | Stack | Use |
|---|---|---|
| `--font-ui` | HarmonyOS Sans SC → MiSans → Noto Sans SC → system | All UI text |
| `--font-mono` | JetBrains Mono → Cascadia → Consolas | Device ids, values, timestamps, badges (`.mono`) |

Scale: `--fs-xs` 0.72rem · `--fs-sm` 0.82rem · `--fs-md` 0.92rem ·
`--fs-lg` 1.05rem · `--fs-xl` 1.5rem. Anything a machine produced
(ids, readings, times) is set in mono; anything a human reads is UI sans.

## Shape, spacing, motion

- Radius: `--radius` 10px (cards), `--radius-sm` 6px (chips/inputs)
- Grid gap and card padding: `--gap` / `--pad` = 14px
- Motion: one easing (`--ease`); animation is reserved for *state changes*
  (critical beacon throb, hazard stripe crawl, alert row entry, correlation
  wire flow). `prefers-reduced-motion` disables all of it.

## Component inventory

| Component | Role |
|---|---|
| `SystemPulse` | Hero status strip + 4 KPIs (devices, msgs/10min, active alerts, semantic gate) |
| `CrossAlertBanner` | Correlated event banner with node edge causal chain; renders only when a `cross_subsystem` alert is active (< 60s) |
| `KnowledgeGraph` | ECharts force graph: factory → subsystems → sensors → observed properties, from `/api/v1/semantic`; alerted sensors pulse red |
| `DeviceCard` | Shared card shell with protocol badge |
| `AlertsPanel` | Live feed; cross alerts get a `CROSS` badge + outlined row |
| `ConsoleLayout` / `StatusBar` | App shell (tabs, clock, adapter lamps) |

## Demo mode

`?demo=1` (e.g. `http://localhost:5173/?demo=1`) intercepts API calls in
`src/demo.ts` and plays a scripted scenario: ~20s normal → temperature and
CO rise together → warnings → hardlimits criticals → cross subsystem
**fire risk** correlation. Use it for design review, stage demos, and
screenshots without a backend. Remove the param to use the real API.

## Extending (for teammates)

- New panel: wrap it in `DeviceCard`, use tokens for every color, put
  machine values in `.mono`.
- New alert type: if the backend emits a new `subsystem`, `AlertsPanel`
  renders it automatically; add a badge rule only if it needs distinct
  treatment.
- New chart: pull colors with
  `getComputedStyle(document.documentElement).getPropertyValue('--data-1')`
  the way `KnowledgeGraph.vue` does, so charts follow the token system.

## v1.1 Knowledge graph interactivity (team feedback round 1)

Changes:
- **KnowledgeGraph** is now full width (460px), draggable, with a *data
  heartbeat*: sensor nodes glow briefly when a measurement newer than 6s
  arrives, so the graph visibly beats with live traffic.
- **GateBadge** in the graph header shows the live SHACL gate:
  `✓ SHACL PASSED` / `✗ SHACL REJECTED` (with the rejection reason on
  hover), or a neutral `SHACL · 待接入` state while the endpoint is absent.
- **SparqlPanel** replaces the static semantic table: five preset chips
  (mirroring `backend/api/semantic.py` VIEWS) show and run the real SPARQL;
  the textarea is editable and edited queries go to the custom endpoint.

### Backend endpoints the frontend now expects (for the gate branch)

1. `GET /api/v1/semantic/gate-status` → latest SHACL gate outcome:

```json
{
  "status": "passed" | "rejected",
  "checked_at": "ISO-8601",
  "last_device": "sensor_mq2_01",
  "reason": "only when rejected — pyshacl message",
  "passed_count": 123,
  "rejected_count": 4
}
```

`404` is handled gracefully (badge shows the pending state), so merging the
frontend before the backend is safe.

2. `POST /api/v1/semantic/query` with `{"query": "<sparql>"}` → raw SPARQL
JSON results (`head.vars` + `results.bindings`), i.e. Fuseki's response
passed through. `404`/`405` produce a friendly "endpoint pending" message
and preset queries keep working, so this too can merge ahead of the backend.
