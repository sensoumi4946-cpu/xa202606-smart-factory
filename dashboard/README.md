# Dashboard

Vue 3 + Vite + ECharts frontend for the XA-202606 smart-factory safety platform.

## Main views

- Dashboard overview
- Wallboard
- Device manager
- Alerts
- Prediction/trend display
- Knowledge graph
- SPARQL/semantic tools
- System status
- API/debug console
- Control interaction

## Security boundary

The dashboard may submit `ControlRequest`, but it must not construct or store the downstream command-signing secret. HMAC command signing belongs to the backend.

Use the backend API key through the intended session/runtime mechanism; never hard-code real credentials into source.

## Development

```bash
cd dashboard
npm install
npm run dev
```

Default dev port:

```text
5173
```

Build and test:

```bash
npm test -- --run
npm run build
```