# Implementation Plan: FastAPI + React Frontend for codesub

## Overview

Build a web interface for managing codesub subscriptions consisting of:
1. **FastAPI backend** (`src/codesub/api.py`) - REST API that wraps existing `ConfigStore` operations
2. **React frontend** (`frontend/`) - Single-page application using Vite
3. **CLI integration** - New `codesub serve` command to start the API server

The architecture reuses all existing business logic from `ConfigStore`, `GitRepo`, and validation utilities. The API layer is a thin wrapper that translates HTTP requests to `ConfigStore` method calls and handles error mapping.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Reuse `ConfigStore` directly | All CRUD logic exists; no need to duplicate |
| Pydantic models for API schemas | FastAPI integration, automatic validation, OpenAPI docs |
| Map `CodesubError` to HTTP errors | Consistent error handling with proper status codes |
| CORS with localhost origins | Required for local dev (Vite runs on different port) |
| Vite + React | Fast dev experience, modern tooling, simple setup |
| TypeScript for frontend | Type safety, better IDE support |
| Manual path entry | Per requirements (no visual file browser) |
| Static file serving from FastAPI | Single deployment artifact option |

## File Structure (New Files)

```
/Users/vlad/dev/projects/codesub/
├── src/codesub/
│   ├── api.py          # FastAPI application and routes
│   └── cli.py          # (modified) add "serve" command
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts              # API client functions
│       ├── types.ts            # TypeScript interfaces
│       └── components/
│           ├── SubscriptionList.tsx
│           ├── SubscriptionDetail.tsx
│           ├── SubscriptionForm.tsx
│           └── StatusFilter.tsx
├── tests/
│   └── test_api.py     # API endpoint tests
└── pyproject.toml      # (modified) add fastapi, uvicorn
```

## Implementation Steps

### Step 1: Add Python Dependencies

**File:** `pyproject.toml`

Add `fastapi` and `uvicorn` to dependencies:
```toml
[tool.poetry.dependencies]
python = ">=3.10"
fastapi = ">=0.109.0"
uvicorn = {version = ">=0.27.0", extras = ["standard"]}

[tool.poetry.group.dev.dependencies]
pytest = ">=7.0"
pytest-cov = ">=4.0"
httpx = ">=0.26.0"
```

Run `poetry install` after modification.

---

### Step 2: Create FastAPI Backend (`src/codesub/api.py`)

Create the API module with:

1. **Pydantic Schemas** for request/response validation:
   - `AnchorSchema`, `SubscriptionSchema`
   - `SubscriptionCreateRequest`, `SubscriptionUpdateRequest`
   - `SubscriptionListResponse`, `ErrorResponse`

2. **Helper Functions**:
   - `get_store_and_repo()` - Get ConfigStore and GitRepo instances
   - `subscription_to_schema()` - Convert dataclass to Pydantic model

3. **Global Exception Handler** (cleaner than per-route try/except):
   - `@app.exception_handler(CodesubError)` - Maps all CodesubError subclasses to HTTP responses
   - Returns JSON `{detail, error_type}` with appropriate status codes

4. **FastAPI App** with CORS middleware for localhost origins

5. **Endpoints**:
   - `GET /api/subscriptions` - List subscriptions (includes `baseline_ref` in response)
   - `GET /api/subscriptions/{id}` - Get single subscription
   - `POST /api/subscriptions` - Create subscription (with full validation, see below)
   - `PATCH /api/subscriptions/{id}` - Update subscription
   - `DELETE /api/subscriptions/{id}` - Delete subscription
   - `POST /api/subscriptions/{id}/reactivate` - Reactivate subscription
   - `GET /api/health` - Health check

**Subscription Creation Flow (POST /api/subscriptions)**:
The create endpoint must replicate the validation logic from `cli.py:cmd_add()`:
1. Parse location using `utils.parse_location(request.location)` → (path, start_line, end_line)
2. Load config to get baseline ref: `config = store.load()`
3. Validate file exists at baseline: `lines = repo.show_file(config.repo.baseline_ref, path)`
4. Validate line range: `if end_line > len(lines): raise InvalidLineRangeError(...)`
5. Extract anchors: `context_before, watched_lines, context_after = extract_anchors(lines, start_line, end_line, context=request.context)`
6. Create Anchor and Subscription objects
7. Save via `store.add_subscription(sub)`

**Reactivate Flow (POST /api/subscriptions/{id}/reactivate)**:
Note: `ConfigStore` has no `reactivate_subscription()` method. The API layer will:
1. Get subscription: `sub = store.get_subscription(sub_id)`
2. Check if already active: `if sub.active: raise HTTPException(400, "Already active")`
3. Set active: `sub.active = True`
4. Update: `store.update_subscription(sub)`

**PATCH Semantics (Update Subscription)**:
- **Omitted field** → Keep existing value (use Pydantic `exclude_unset=True`)
- **Empty string `""`** → Clear to `null`
- **Explicit `null`** → Clear to `null`

This prevents accidental data loss when only updating one field.

---

### Step 3: Add CLI `serve` Command (`src/codesub/cli.py`)

Modify CLI to add `serve` subcommand:
- Add `cmd_serve()` function that starts uvicorn server
- Add serve subparser with `--host`, `--port`, `--reload` options
- Register in commands dict
- **Important**: Run with `workers=1` (single worker) to avoid concurrent write issues with ConfigStore. This is a local single-user tool.

---

### Step 4: Create React Frontend - Project Setup

Create `frontend/` directory with:
- `package.json` - Dependencies (react, react-dom, vite, typescript)
- `vite.config.ts` - Vite config with API proxy to localhost:8000 (note: API must run on port 8000 for proxy to work)
- `tsconfig.json` - TypeScript configuration
- `index.html` - Entry HTML file with minimal inline styles

**Styling Approach:** Minimal inline styles for MVP. No CSS framework required for this initial implementation.

---

### Step 5: Create TypeScript Types (`frontend/src/types.ts`)

Define interfaces matching API schemas:
- `Anchor`, `Subscription`
- `SubscriptionListResponse` (includes `baseline_ref: string`)
- `SubscriptionCreateRequest`, `SubscriptionUpdateRequest`
- `ApiError`, `FilterStatus`

---

### Step 6: Create API Client (`frontend/src/api.ts`)

Implement fetch wrapper functions:
- `listSubscriptions(includeInactive)`
- `getSubscription(id)`
- `createSubscription(data)`
- `updateSubscription(id, data)`
- `deleteSubscription(id, hard)`
- `reactivateSubscription(id)`

---

### Step 7: Create React Components

**Entry points:**
- `main.tsx` - ReactDOM render
- `App.tsx` - Main container with routing state, fetch logic, message display

**Components:**
- `StatusFilter.tsx` - Toggle active/all filter
- `SubscriptionList.tsx` - Table of subscriptions with click-to-select
- `SubscriptionDetail.tsx` - Full details view with delete/reactivate actions
- `SubscriptionForm.tsx` - Create/edit form with validation feedback

---

### Step 8: Write API Tests (`tests/test_api.py`)

Create test suite using FastAPI's TestClient:
- `TestListSubscriptions` - Empty list, list with subscriptions
- `TestCreateSubscription` - Success, invalid location, file not found, line out of range
- `TestGetSubscription` - By full ID, by partial ID, not found
- `TestUpdateSubscription` - Update label, update description
- `TestDeleteSubscription` - Soft delete, hard delete
- `TestReactivateSubscription` - Reactivate, already active
- `TestHealthCheck` - Health endpoint

---

## API Design Summary

| Method | Endpoint | Description | Status Codes |
|--------|----------|-------------|--------------|
| GET | `/api/subscriptions` | List subscriptions | 200, 409 |
| GET | `/api/subscriptions/{id}` | Get single subscription | 200, 404, 409 |
| POST | `/api/subscriptions` | Create subscription | 201, 400, 404, 409 |
| PATCH | `/api/subscriptions/{id}` | Update label/description | 200, 404, 409 |
| DELETE | `/api/subscriptions/{id}` | Delete (soft/hard) | 200, 404, 409 |
| POST | `/api/subscriptions/{id}/reactivate` | Reactivate | 200, 400, 404, 409 |
| GET | `/api/health` | Health check | 200 |

**Query Parameters:**
- `GET /api/subscriptions`: `include_inactive` (bool)
- `DELETE /api/subscriptions/{id}`: `hard` (bool)

**Response Schemas:**
- `GET /api/subscriptions` returns:
  ```json
  {
    "subscriptions": [...],
    "count": 5,
    "baseline_ref": "abc123..."
  }
  ```

---

## Frontend Components Summary

| Component | Purpose |
|-----------|---------|
| `App.tsx` | Main container, routing state, fetch/refresh logic |
| `StatusFilter.tsx` | Toggle active/all filter |
| `SubscriptionList.tsx` | Table of subscriptions |
| `SubscriptionDetail.tsx` | Full details view, delete/reactivate actions |
| `SubscriptionForm.tsx` | Create/edit form with validation feedback |

---

## Error Handling

**Implementation**: Use a global `@app.exception_handler(CodesubError)` instead of try/except in each route. This ensures consistent error responses and reduces duplication.

**Exception to HTTP Status Mapping:**
- `ConfigNotFoundError` → 409 (Conflict) - "Run codesub init first"
- `SubscriptionNotFoundError` → 404 (Not Found)
- `InvalidLocationError` → 400 (Bad Request)
- `InvalidLineRangeError` → 400 (Bad Request)
- `FileNotFoundAtRefError` → 404 (Not Found)
- `InvalidSchemaVersionError` → 500 (Internal Server Error) - config file corrupted/incompatible
- `NotAGitRepoError` → 500 (Internal Server Error) - server not started in a git repo
- `GitError` → 500 (Internal Server Error) - git command failed
- Other `CodesubError` → 500 (Internal Server Error)

**Note**: `/api/health` always returns 200 and includes `config_initialized: bool` for status checks.

---

## Edge Cases Considered

- **Config not initialized**: API returns 409 with "Run codesub init first"; health endpoint reports `config_initialized: false`
- **File not in repo**: Returns 404 with descriptive error from `FileNotFoundAtRefError`
- **Line range exceeds file**: Returns 400 with line count information
- **Ambiguous partial ID**: Returns 404 with "ambiguous" in message (existing behavior)
- **Reactivate active subscription**: Returns 400 with explanation
- **Empty label/description**: Stored as `null`, displayed as "-" in UI

---

## Testing Strategy

- API unit tests via `TestClient` (covered in `test_api.py`)
- Test CRUD operations: create, read, update, soft delete, hard delete
- Test error cases: invalid location, file not found, subscription not found
- Test edge cases: partial ID matching, reactivate already-active
- Frontend: manual testing during development
- Integration: run `codesub serve` and verify frontend connects

---

## Usage After Implementation

```bash
# Install dependencies
poetry install
cd frontend && npm install

# Development mode (two terminals)
# Terminal 1: API server with auto-reload
codesub serve --reload

# Terminal 2: Frontend dev server
cd frontend && npm run dev

# Production build
cd frontend && npm run build
# Serve frontend from FastAPI or copy build to static hosting
```
