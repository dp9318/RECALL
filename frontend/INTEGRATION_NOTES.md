# Frontend integration notes

This dashboard is expected to talk to the RECALL HTTP/JSON API and not to SQLite, ChromaDB, or the core services directly.

Current state:

- The repository now includes a working FastAPI HTTP server for the dashboard.
- The frontend defaults to the real API client unless mock mode is explicitly enabled using `VITE_USE_MOCK_API=true`.
- Mock data remains available only as an explicit opt-in for isolated UI development.
- Connection health and API errors are treated as real signals; they do not silently fall back to mock data.

Verified runtime configuration:

- API startup: `python -m core.recall_core.api` or `uvicorn core.recall_core.api:app --host 0.0.0.0 --port 8080`
- Default API base URL: `http://localhost:8080`
- Override via `VITE_API_BASE_URL` when running the dashboard against a non-default backend.

Verified route surface:

- `GET /health`
- `GET /projects`
- `GET /memories`
- `GET /memories/{id}`
- `POST /memories`
- `PATCH /memories/{id}`
- `DELETE /memories/{id}`
- `GET /custom-instructions`
- `POST /custom-instructions`
- `PATCH /custom-instructions/{id}`
- `DELETE /custom-instructions/{id}`
- `GET /conflicts`
- `GET /sessions`
- `GET /stats`
- `POST /context/query`
- `POST /context/compact`

This API is backed by the existing RECALL core, repository stack, and SQLite canonical storage. ChromaDB remains a derived semantic index and is not the canonical memory source.
