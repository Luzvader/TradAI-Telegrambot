# TradAI Angular Dashboard

Angular SPA used by FastAPI for the web dashboard.

## Development

```bash
npm install
npm start
```

The app runs on `http://localhost:4200`.

If you need API proxying in local-only frontend mode, use your browser with CORS-aware setup or run against the same host as FastAPI.

## Production Build

```bash
npm run build
```

FastAPI expects the generated files at:
`frontend/dist/tradai-dashboard/browser/`
