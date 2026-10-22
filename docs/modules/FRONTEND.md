# RECALL — Frontend Web Dashboard Module Contract

## 1. Goal

Provide a modern, responsive, human-facing control surface for exploring agent memories, inspecting lineage graphs, managing user-authored custom instructions, and arbitrating detected memory conflicts.

---

## 2. Technology Stack & Build Pipeline

- **Core Framework**: React 19 (`react: ^19.3.0`, `react-dom: ^19.3.0`)
- **Language**: TypeScript (`~6.0.2`, strict mode)
- **Styling**: Tailwind CSS v4 (`@tailwindcss/vite: ^4.3.3`, `tailwindcss: ^4.3.3`)
- **Routing**: React Router v7 (`react-router-dom: ^7.18.4`)
- **Icons**: React Icons / Lucide (`react-icons: ^5.7.0`)
- **Bundler & Dev Server**: Vite (`^8.3.4`)

```bash
# Development server (runs on http://localhost:5173):
npm run dev

# Production build & strict typecheck:
npm run build
```

---

## 3. Application Structure & Page Routes

Entry point: `frontend/src/main.tsx` mounting `frontend/src/App.tsx`.

```text
frontend/src/
├── api/                  # Unified HTTP API client & mock client
│   ├── client.ts         # Authoritative REST client connecting to http://localhost:8080
│   ├── mockClient.ts     # In-memory mock client for standalone UI testing
│   └── index.ts          # Environment-driven client export (VITE_USE_MOCK_API)
├── components/           # Reusable UI component library
│   ├── layout/           # AppShell, Header, Sidebar, ProjectSelector
│   └── ui/               # Button, Modal, Card, Input, Badge, Avatar, Skeleton
├── pages/                # Primary route views
│   ├── OverviewPage.tsx              # System metrics, recent memories & quick actions
│   ├── MemoryExplorerPage.tsx        # Searchable, filtered memory catalogue
│   ├── MemoryDetailPage.tsx          # Full memory view & interactive lineage graph
│   ├── CreateMemoryPage.tsx          # Manual memory capture form
│   ├── EditMemoryPage.tsx            # Memory update & tags editor
│   ├── ConflictCenterPage.tsx        # Conflict detection & arbitration interface
│   ├── CustomInstructionsPage.tsx    # Scope-aware user instruction management
│   ├── ChatPage.tsx                  # "Ask RECALL" interactive query interface
│   └── SettingsPage.tsx              # Diagnostics, version info, and project management
└── types/                # TypeScript DTOs matching backend JSON contracts
```

---

## 4. API Client & Mock Mode Architecture

The frontend communicates with the backend exclusively through the typed client interface in `frontend/src/api/`:

```typescript
// Controlled via environment variable:
const USE_MOCK = import.meta.env.VITE_USE_MOCK_API === 'true';
export const api: ApiClient = USE_MOCK ? mockApi : realApi;
```

### Invariant Rules:
1. **Zero Direct Persistence Access**: The frontend never directly imports SQLite, ChromaDB, or core backend code.
2. **Encapsulated Communication**: All mutations route through the standardized FastAPI REST endpoints documented in `docs/modules/API.md`.
3. **Graceful Degradation**: Clear loading spinners, empty states, error toasts, and fallback placeholders are rendered for all network calls.
