# Frontend integration notes

This dashboard is expected to talk to the RECALL HTTP/JSON API and not to SQLite, ChromaDB, or the core services directly.

Current state:

- The repository now includes a working FastAPI HTTP server for the dashboard.
- The frontend defaults to the real API client unless mock mode is explicitly enabled using `VITE_USE_MOCK_API=true`.
- Mock data remains available only as an explicit opt-in for isolated UI development.
- Connection health and API errors are treated as real signals; they do not silently fall back to mock data.
- FastAPI handlers keep synchronous Core operations on the event-loop thread because the SQLite Unit of Work owns a thread-affine connection.
- Health reports API reachability separately from database, ChromaDB, and configured Ollama model availability. A failed health request leaves dependency status unknown rather than marking every dependency unavailable.

Verified runtime configuration:

- API startup: `python -m core.recall_core.api` or `uvicorn core.recall_core.api:app --host 0.0.0.0 --port 8080`
- In Vite development, requests use the same-origin `/api` path and proxy to `http://localhost:8080`; the proxy strips `/api` to match the Core routes.
- Set `VITE_API_PROXY_TARGET` to change the Vite development proxy target, for example when testing against an isolated API instance.
- In production, the API base URL defaults to `http://localhost:8080`.
- Set `VITE_API_BASE_URL` to explicitly override the API base URL in either environment. In development, the explicit value bypasses the Vite proxy.
- For a direct cross-origin API URL, configure the dashboard's exact browser origin in `RECALL_CORS_ORIGINS`; the default same-origin development proxy does not require cross-origin CORS access.

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
