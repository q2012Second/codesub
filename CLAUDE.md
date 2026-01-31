# codesub - Code Subscription Tool

A Python CLI tool that lets you "subscribe" to code sections, detect changes via git diff, and keep subscriptions valid across line shifts and file renames.

Supports two subscription types:
- **Line-based**: Track line ranges (e.g., `config.py:10-25`)
- **Semantic**: Track code constructs by identity (e.g., `auth.py::User.validate`)

## Development

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run CLI
poetry run codesub --help

# Start servers (backend + frontend)
task dev

# Initialize mock repository for testing
task mock:init
```

## Task Commands

### Development
| Task | Description |
|------|-------------|
| `task dev` | Start backend + frontend servers |
| `task dev:backend` | Start FastAPI backend only |
| `task dev:frontend` | Start Vite frontend only |
| `task stop` | Stop running servers |
| `task shell` | IPython shell with codesub modules preloaded |

### Testing & Quality
| Task | Description |
|------|-------------|
| `task test` | Run all tests |
| `task test -- -k "name"` | Run specific tests |
| `task test:cov` | Run with coverage report |
| `task test:unit` | Unit tests only |
| `task test:integration` | Integration tests only |
| `task lint` | Run linters (ruff + mypy) |
| `task format` | Auto-format code |
| `task format:check` | Check formatting (CI-friendly) |

### Mock Repositories
| Task | Description |
|------|-------------|
| `task mock:init` | Initialize both mock repos (Python + Java) |
| `task mock:init:python` | Initialize Python mock repo |
| `task mock:init:java` | Initialize Java mock repo |
| `task mock:reset` | Reset both mock repos |
| `task mock:reset:python` | Reset Python mock repo |
| `task mock:reset:java` | Reset Java mock repo |

### Codesub Operations
| Task | Description |
|------|-------------|
| `task codesub:add TARGET=path -- file:10-20` | Add subscription |
| `task codesub:list TARGET=path` | List subscriptions |
| `task codesub:clean` | Remove all projects, subscriptions, and history |
| `task codesub:scan TARGET=path` | Scan for changes |
| `task codesub:scan:ci TARGET=path` | Scan with CI exit codes |
| `task codesub:apply TARGET=path` | Apply update proposals |

### Build & CI
| Task | Description |
|------|-------------|
| `task setup` | Install all dependencies |
| `task build` | Build backend + frontend |
| `task ci` | Run CI checks (lint + test) |
| `task clean` | Clean build artifacts |

## Project Structure

```
src/codesub/
├── cli.py            # CLI interface (argparse)
├── api.py            # FastAPI REST API server
├── models.py         # Data models (Subscription, SemanticTarget, Anchor, Config, Project)
├── config_store.py   # Per-project JSON config management (data/subscriptions/)
├── project_store.py  # Multi-project registration (data/projects.json)
├── scan_history.py   # Scan history storage (data/scan_history/)
├── git_repo.py       # Git wrapper
├── diff_parser.py    # Unified diff parsing
├── detector.py       # Trigger detection (line-based and semantic)
├── update_doc.py     # Update document generation
├── updater.py        # Apply proposals to subscriptions
├── utils.py          # Target parsing (LineTarget, SemanticTargetSpec)
├── errors.py         # Custom exceptions
└── semantic/         # Semantic code analysis (Tree-sitter based)
    ├── __init__.py
    ├── construct.py      # Construct dataclass
    ├── fingerprint.py    # Hash computation (interface_hash, body_hash)
    ├── indexer_protocol.py # SemanticIndexer protocol
    ├── registry.py       # Language indexer registry
    ├── python_indexer.py # Python construct extraction
    └── java_indexer.py   # Java construct extraction

frontend/             # React + TypeScript frontend
mock_repos/           # Mock repositories for testing
├── python/           # Python e-commerce API (run `task mock:init:python`)
└── java/             # Java e-commerce API (run `task mock:init:java`)
tests/                # Test suite (pytest, 260+ tests)
data/                 # Local data directory (gitignored)
├── projects.json     # Registered projects
├── subscriptions/    # Per-project subscription config
│   └── <project_id>/ # subscriptions.json per project
└── scan_history/     # Scan results per project
```

## CLI Usage

```bash
# Register a git repo (auto-initializes config)
codesub projects add .

# Subscribe to a line range
codesub add path/to/file.py:42-50 --label "Important function"

# Subscribe to a semantic target (code construct)
codesub add path/to/file.py::ClassName.method --label "Track method"
codesub add config.py::API_VERSION --label "Track constant"

# List discoverable constructs in a file
codesub symbols path/to/file.py
codesub symbols path/to/file.py --kind method --grep validate

# List subscriptions
codesub list

# Scan for changes (compare baseline to HEAD)
codesub scan --write-updates updates.json

# Apply proposed updates
codesub apply-updates updates.json

# Multi-project management
codesub projects list [--json]
codesub projects add <path> [--name NAME]
codesub projects remove <project_id>

# Scan history management
codesub scan-history clear [--project PROJECT_ID]
```

## Semantic Subscriptions

Semantic subscriptions track code constructs by identity using Tree-sitter parsing.

**Target format**: `path/to/file.py::QualifiedName` or `path/to/file.py::kind:QualifiedName`

**Supported languages**: Python, Java

**Supported constructs (Python)**:
- Module variables/constants: `config.py::API_VERSION`
- Class fields: `models.py::User.email`
- Methods: `auth.py::User.validate`
- Enum members: `types.py::Status.PENDING`
- Dataclass fields: `models.py::Config.timeout`

**Supported constructs (Java)**:
- Classes/interfaces/enums: `Service.java::OrderService`
- Fields: `Config.java::AppConfig.API_VERSION`
- Methods (with param types): `Service.java::OrderService.process(Order,User)`
- Constructors: `User.java::User.User(String,String)`
- Enum constants: `Status.java::OrderStatus.PENDING`

**Change detection**:
- `structural`: Type annotation or signature changed
- `content`: Value or body changed
- `missing`: Construct deleted

**Fingerprinting**: Uses `interface_hash` (type/signature) and `body_hash` (value/body) for change classification.

## API Endpoints

### Projects
- `GET /api/projects` - List all registered projects
- `POST /api/projects` - Add a project (auto-initializes config)
- `GET /api/projects/{id}` - Get project status
- `PATCH /api/projects/{id}` - Update project name
- `DELETE /api/projects/{id}` - Remove project (with data cleanup)

### Project Subscriptions
- `GET /api/projects/{id}/subscriptions` - List subscriptions
- `POST /api/projects/{id}/subscriptions` - Create subscription
- `GET /api/projects/{id}/subscriptions/{sub_id}` - Get subscription
- `PATCH /api/projects/{id}/subscriptions/{sub_id}` - Update subscription
- `DELETE /api/projects/{id}/subscriptions/{sub_id}` - Delete subscription
- `POST /api/projects/{id}/subscriptions/{sub_id}/reactivate` - Reactivate

### Scans
- `POST /api/projects/{id}/scan` - Run scan
- `POST /api/projects/{id}/apply-updates` - Apply proposals

### Scan History
- `GET /api/projects/{id}/scan-history` - List scan history
- `GET /api/projects/{id}/scan-history/{scan_id}` - Get scan result
- `DELETE /api/projects/{id}/scan-history` - Clear project history
- `DELETE /api/scan-history` - Clear all history

### Code Browser (for visual subscription creation)
- `GET /api/projects/{id}/files` - List git-tracked files (with search, pagination)
- `GET /api/projects/{id}/file-content?path=` - Get file content with lines
- `GET /api/projects/{id}/file-symbols?path=` - Get semantic constructs in file

## Data Storage

All data is stored centrally in `data/` (configurable via `CODESUB_DATA_DIR` env var):
- `data/projects.json` - Registered projects
- `data/subscriptions/<project_id>/subscriptions.json` - Per-project subscriptions and config
- `data/scan_history/<project_id>/<scan_id>.json` - Scan results

**Note**: Target git repos remain clean (no `.codesub/` directory). If a legacy `.codesub/` exists, it will be auto-migrated on first access.
