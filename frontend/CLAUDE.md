# codesub Frontend

React + TypeScript frontend for managing codesub subscriptions across multiple projects.

## Development

```bash
# From codesub root
task dev:frontend    # Start Vite dev server on :5173
task dev             # Start both backend (:8000) and frontend (:5173)
task stop            # Stop all servers
```

## Architecture

### Multi-Project Design

The frontend manages subscriptions across multiple git repositories:
- Projects are registered via manual path input
- Project selector in header for quick switching
- Each project has its own subscriptions, scans, and history

### Tech Stack

- React 18 + TypeScript
- Vite for bundling
- No CSS framework - inline styles
- No state management library - useState/useEffect

## Project Structure

```
src/
├── App.tsx              # Main app with view routing and project context
├── api.ts               # API client functions
├── types.ts             # TypeScript interfaces
├── main.tsx             # Entry point
└── components/
    ├── StatusFilter.tsx       # Active/All filter toggle
    ├── SubscriptionList.tsx   # Subscription list view
    ├── SubscriptionDetail.tsx # Subscription detail with anchors
    ├── SubscriptionForm.tsx   # Create/Edit subscription form
    ├── ProjectList.tsx        # Project list view
    ├── ProjectForm.tsx        # Add project form (path input)
    ├── ProjectSelector.tsx    # Header dropdown for switching projects
    ├── ScanView.tsx           # Run scans, view results, apply updates
    ├── ScanHistoryList.tsx    # View past scan results
    └── ApplyUpdatesModal.tsx  # Confirmation dialog for applying proposals
```

## Views

App.tsx manages these views via `view` state:

| View | Component | Description |
|------|-----------|-------------|
| `projects` | ProjectList | Main view - shows all registered projects |
| `project-add` | ProjectForm | Add a new project by path |
| `list` | SubscriptionList | Subscriptions for selected project |
| `detail` | SubscriptionDetail | Single subscription with anchors |
| `create` | SubscriptionForm | New subscription form |
| `edit` | SubscriptionForm | Edit label/description |
| `scan` | ScanView | Run scans and view results |
| `scan-history` | ScanHistoryList | View past scan results |

## API Integration

All API calls go through `api.ts`. Base URL: `/api` (proxied to backend in dev).

### Subscription APIs
| Function | Endpoint | Method |
|----------|----------|--------|
| `listSubscriptions(includeInactive)` | `/api/subscriptions` | GET |
| `getSubscription(id)` | `/api/subscriptions/:id` | GET |
| `createSubscription(data)` | `/api/subscriptions` | POST |
| `updateSubscription(id, data)` | `/api/subscriptions/:id` | PATCH |
| `deleteSubscription(id, hard)` | `/api/subscriptions/:id` | DELETE |
| `reactivateSubscription(id)` | `/api/subscriptions/:id/reactivate` | POST |

### Project APIs
| Function | Endpoint | Method |
|----------|----------|--------|
| `listProjects()` | `/api/projects` | GET |
| `addProject(path, name?)` | `/api/projects` | POST |
| `getProjectStatus(id)` | `/api/projects/:id` | GET |
| `updateProject(id, name)` | `/api/projects/:id` | PATCH |
| `removeProject(id)` | `/api/projects/:id` | DELETE |
| `listProjectSubscriptions(id, includeInactive)` | `/api/projects/:id/subscriptions` | GET |

### Scan APIs
| Function | Endpoint | Method |
|----------|----------|--------|
| `runScan(projectId, baseRef?, targetRef?)` | `/api/projects/:id/scan` | POST |
| `listScanHistory(projectId, limit?)` | `/api/projects/:id/scan-history` | GET |
| `getScanResult(projectId, scanId)` | `/api/projects/:id/scan-history/:scanId` | GET |
| `clearProjectScanHistory(projectId)` | `/api/projects/:id/scan-history` | DELETE |
| `clearAllScanHistory()` | `/api/scan-history` | DELETE |
| `applyUpdates(projectId, proposalIds)` | `/api/projects/:id/apply-updates` | POST |

## Key Types (types.ts)

```typescript
interface Project {
  id: string;
  name: string;
  path: string;
  created_at: string;
  updated_at: string;
}

interface Subscription {
  id: string;
  path: string;
  start_line: number;
  end_line: number;
  label: string | null;
  description: string | null;
  anchors: Anchor | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

interface ScanResult {
  base_ref: string;
  target_ref: string;
  triggers: Trigger[];
  proposals: Proposal[];
  unchanged: { subscription_id: string }[];
}

interface ScanHistoryEntry {
  id: string;
  project_id: string;
  base_ref: string;
  target_ref: string;
  trigger_count: number;
  proposal_count: number;
  unchanged_count: number;
  created_at: string;
}
```

## Vite Config

- Dev server: port 5173
- API proxy: `/api` -> `http://localhost:8000/api`

## Features

1. **Multi-project management** - Register and switch between multiple git repos
2. **Subscription management** - Create, edit, delete, reactivate subscriptions
3. **Scan functionality** - Run scans against different git refs (HEAD~1, baseline, custom)
4. **Apply updates** - Apply proposals from scan results with confirmation dialog
5. **Scan history** - View past scans with summaries, clear history
