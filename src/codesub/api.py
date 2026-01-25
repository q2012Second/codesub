"""FastAPI REST API for codesub subscription management."""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from .config_store import ConfigStore
from .errors import (
    CodesubError,
    ConfigNotFoundError,
    SubscriptionNotFoundError,
    InvalidLocationError,
    InvalidLineRangeError,
    FileNotFoundAtRefError,
    InvalidSchemaVersionError,
    NotAGitRepoError,
    GitError,
    ProjectNotFoundError,
    InvalidProjectPathError,
    ScanNotFoundError,
)
from .git_repo import GitRepo
from .models import Anchor, Subscription
from .utils import parse_location, extract_anchors
from .project_store import ProjectStore
from .scan_history import ScanHistory
from .detector import Detector
from .updater import Updater
from .update_doc import result_to_dict


# --- Pydantic Schemas ---


class AnchorSchema(BaseModel):
    context_before: list[str]
    lines: list[str]
    context_after: list[str]


class SubscriptionSchema(BaseModel):
    id: str
    path: str
    start_line: int
    end_line: int
    label: Optional[str] = None
    description: Optional[str] = None
    anchors: Optional[AnchorSchema] = None
    active: bool = True
    created_at: str
    updated_at: str


class SubscriptionCreateRequest(BaseModel):
    """Request body for creating a subscription."""

    location: str = Field(..., description="path:line or path:start-end format")
    label: Optional[str] = None
    description: Optional[str] = None
    context: int = Field(default=2, ge=0, le=10)


class SubscriptionUpdateRequest(BaseModel):
    """Request body for updating a subscription."""

    label: Optional[str] = None
    description: Optional[str] = None


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionSchema]
    count: int
    baseline_ref: str
    baseline_title: str = ""


class ErrorResponse(BaseModel):
    detail: str
    error_type: str


# --- Project Schemas ---


class ProjectSchema(BaseModel):
    id: str
    name: str
    path: str
    created_at: str
    updated_at: str


class ProjectCreateRequest(BaseModel):
    path: str = Field(..., description="Absolute path to git repository")
    name: Optional[str] = Field(None, description="Display name (defaults to dir name)")


class ProjectUpdateRequest(BaseModel):
    name: str = Field(..., description="New display name")


class ProjectListResponse(BaseModel):
    projects: list[ProjectSchema]
    count: int


class ProjectStatusResponse(BaseModel):
    project: ProjectSchema
    path_exists: bool
    codesub_initialized: bool
    subscription_count: int
    baseline_ref: Optional[str]


# --- Scan Schemas ---


class ScanRequest(BaseModel):
    base_ref: str = Field(..., description="Base git ref (e.g., 'HEAD~1', 'baseline', commit hash)")
    target_ref: Optional[str] = Field(default="HEAD", description="Target git ref ('HEAD', commit hash), or empty/null for working directory")


class TriggerSchema(BaseModel):
    subscription_id: str
    path: str
    start_line: int
    end_line: int
    reasons: list[str]
    label: Optional[str]


class ProposalSchema(BaseModel):
    subscription_id: str
    old_path: str
    old_start: int
    old_end: int
    new_path: str
    new_start: int
    new_end: int
    reasons: list[str]
    confidence: str
    shift: Optional[int]
    label: Optional[str]


class ScanResultSchema(BaseModel):
    base_ref: str
    target_ref: str
    triggers: list[TriggerSchema]
    proposals: list[ProposalSchema]
    unchanged_count: int


class ScanHistoryEntrySchema(BaseModel):
    id: str
    project_id: str
    base_ref: str
    target_ref: str
    trigger_count: int
    proposal_count: int
    unchanged_count: int
    created_at: str


class ScanHistoryListResponse(BaseModel):
    scans: list[ScanHistoryEntrySchema]
    count: int


class ApplyUpdatesRequest(BaseModel):
    scan_id: str = Field(..., description="Scan ID to apply proposals from")
    proposal_ids: Optional[list[str]] = Field(
        None,
        description="Specific proposal IDs to apply (all if not specified)"
    )


class ApplyUpdatesResponse(BaseModel):
    applied: list[str]
    warnings: list[str]
    new_baseline: Optional[str]


# --- Helper Functions ---


def get_project_store() -> ProjectStore:
    """Get the global ProjectStore."""
    return ProjectStore()


def get_scan_history() -> ScanHistory:
    """Get the global ScanHistory."""
    return ScanHistory()


def get_project_store_and_repo(project_id: str) -> tuple[ConfigStore, GitRepo]:
    """Get ConfigStore and GitRepo for a specific project."""
    project_store = get_project_store()
    project = project_store.get_project(project_id)

    repo = GitRepo(project.path)
    store = ConfigStore(repo.root)
    return store, repo


def get_store_and_repo() -> tuple[ConfigStore, GitRepo]:
    """Get ConfigStore and GitRepo for the current directory."""
    repo = GitRepo()
    store = ConfigStore(repo.root)
    return store, repo


def subscription_to_schema(sub: Subscription) -> SubscriptionSchema:
    """Convert dataclass Subscription to Pydantic schema."""
    anchors = None
    if sub.anchors:
        anchors = AnchorSchema(
            context_before=sub.anchors.context_before,
            lines=sub.anchors.lines,
            context_after=sub.anchors.context_after,
        )
    return SubscriptionSchema(
        id=sub.id,
        path=sub.path,
        start_line=sub.start_line,
        end_line=sub.end_line,
        label=sub.label,
        description=sub.description,
        anchors=anchors,
        active=sub.active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


# --- FastAPI App ---


app = FastAPI(
    title="codesub API",
    description="REST API for managing code subscriptions",
    version="0.1.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global Exception Handler ---


# Map exception types to HTTP status codes
ERROR_STATUS_CODES: dict[type, int] = {
    ConfigNotFoundError: 409,
    SubscriptionNotFoundError: 404,
    InvalidLocationError: 400,
    InvalidLineRangeError: 400,
    FileNotFoundAtRefError: 404,
    InvalidSchemaVersionError: 500,
    NotAGitRepoError: 500,
    GitError: 500,
    ProjectNotFoundError: 404,
    InvalidProjectPathError: 400,
    ScanNotFoundError: 404,
}


@app.exception_handler(CodesubError)
async def codesub_error_handler(request: Request, exc: CodesubError) -> JSONResponse:
    """Map CodesubError subclasses to appropriate HTTP responses."""
    status_code = ERROR_STATUS_CODES.get(type(exc), 500)
    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc), "error_type": type(exc).__name__},
    )


# --- Endpoints ---


@app.get("/api/subscriptions", response_model=SubscriptionListResponse)
def list_subscriptions(include_inactive: bool = Query(default=False)):
    """List all subscriptions, optionally including inactive ones."""
    store, repo = get_store_and_repo()
    config = store.load()
    subs = store.list_subscriptions(include_inactive=include_inactive)
    baseline_title = repo.commit_title(config.repo.baseline_ref) if config.repo.baseline_ref else ""
    return SubscriptionListResponse(
        subscriptions=[subscription_to_schema(s) for s in subs],
        count=len(subs),
        baseline_ref=config.repo.baseline_ref,
        baseline_title=baseline_title,
    )


@app.get("/api/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def get_subscription(sub_id: str):
    """Get a single subscription by ID (supports partial ID matching)."""
    store, _ = get_store_and_repo()
    sub = store.get_subscription(sub_id)
    return subscription_to_schema(sub)


@app.post("/api/subscriptions", response_model=SubscriptionSchema, status_code=201)
def create_subscription(request: SubscriptionCreateRequest):
    """Create a new subscription."""
    store, repo = get_store_and_repo()
    config = store.load()

    # Parse and validate location
    path, start_line, end_line = parse_location(request.location)

    # Validate file exists at baseline
    baseline = config.repo.baseline_ref
    lines = repo.show_file(baseline, path)

    # Validate line range
    if end_line > len(lines):
        raise InvalidLineRangeError(
            start_line, end_line, f"exceeds file length ({len(lines)} lines)"
        )

    # Extract anchors
    context_before, watched_lines, context_after = extract_anchors(
        lines, start_line, end_line, context=request.context
    )
    anchors = Anchor(
        context_before=context_before,
        lines=watched_lines,
        context_after=context_after,
    )

    # Create subscription
    sub = Subscription.create(
        path=path,
        start_line=start_line,
        end_line=end_line,
        label=request.label,
        description=request.description,
        anchors=anchors,
    )

    store.add_subscription(sub)
    return subscription_to_schema(sub)


@app.patch("/api/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def update_subscription(sub_id: str, request: SubscriptionUpdateRequest):
    """Update subscription label and/or description.

    PATCH semantics:
    - Omitted field: keep existing value
    - Empty string "": clear to null
    - Explicit null: clear to null
    """
    store, _ = get_store_and_repo()
    sub = store.get_subscription(sub_id)

    # Get the fields that were actually sent in the request
    update_data = request.model_dump(exclude_unset=True)

    # Update fields if provided
    if "label" in update_data:
        # Empty string becomes None
        sub.label = request.label if request.label else None
    if "description" in update_data:
        # Empty string becomes None
        sub.description = request.description if request.description else None

    store.update_subscription(sub)
    return subscription_to_schema(sub)


@app.delete("/api/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def delete_subscription(sub_id: str, hard: bool = Query(default=False)):
    """Delete (deactivate or hard delete) a subscription."""
    store, _ = get_store_and_repo()
    sub = store.remove_subscription(sub_id, hard=hard)
    return subscription_to_schema(sub)


@app.post("/api/subscriptions/{sub_id}/reactivate", response_model=SubscriptionSchema)
def reactivate_subscription(sub_id: str):
    """Reactivate a deactivated subscription."""
    store, _ = get_store_and_repo()
    sub = store.get_subscription(sub_id)

    if sub.active:
        raise HTTPException(status_code=400, detail="Subscription is already active")

    sub.active = True
    store.update_subscription(sub)
    return subscription_to_schema(sub)


@app.get("/api/health")
def health_check():
    """Health check endpoint. Always returns 200."""
    try:
        store, repo = get_store_and_repo()
        config_exists = store.exists()
        baseline_ref = None
        if config_exists:
            config = store.load()
            baseline_ref = config.repo.baseline_ref
        return {
            "status": "ok",
            "config_initialized": config_exists,
            "repo_root": str(repo.root),
            "baseline_ref": baseline_ref,
        }
    except NotAGitRepoError:
        return {
            "status": "error",
            "config_initialized": False,
            "detail": "Not running in a git repository",
        }
    except Exception as e:
        return {
            "status": "error",
            "config_initialized": False,
            "detail": str(e),
        }


# --- Project Endpoints ---


@app.get("/api/projects", response_model=ProjectListResponse)
def list_projects():
    """List all registered projects."""
    store = get_project_store()
    projects = store.list_projects()
    return ProjectListResponse(
        projects=[ProjectSchema(**p.to_dict()) for p in projects],
        count=len(projects),
    )


@app.post("/api/projects", response_model=ProjectSchema, status_code=201)
def create_project(request: ProjectCreateRequest):
    """Register a new project."""
    store = get_project_store()
    project = store.add_project(path=request.path, name=request.name)
    return ProjectSchema(**project.to_dict())


@app.get("/api/projects/{project_id}", response_model=ProjectStatusResponse)
def get_project_status(project_id: str):
    """Get project details and status."""
    store = get_project_store()
    status = store.get_project_status(project_id)
    return ProjectStatusResponse(
        project=ProjectSchema(**status["project"]),
        path_exists=status["path_exists"],
        codesub_initialized=status["codesub_initialized"],
        subscription_count=status["subscription_count"],
        baseline_ref=status["baseline_ref"],
    )


@app.patch("/api/projects/{project_id}", response_model=ProjectSchema)
def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update project name."""
    store = get_project_store()
    project = store.update_project(project_id, request.name)
    return ProjectSchema(**project.to_dict())


@app.delete("/api/projects/{project_id}", response_model=ProjectSchema)
def delete_project(project_id: str):
    """Remove a project from the registry."""
    store = get_project_store()
    project = store.remove_project(project_id)
    return ProjectSchema(**project.to_dict())


# --- Project Subscriptions Endpoints ---


@app.get("/api/projects/{project_id}/subscriptions", response_model=SubscriptionListResponse)
def list_project_subscriptions(
    project_id: str,
    include_inactive: bool = Query(default=False)
):
    """List subscriptions for a specific project."""
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    subs = store.list_subscriptions(include_inactive=include_inactive)
    baseline_title = repo.commit_title(config.repo.baseline_ref) if config.repo.baseline_ref else ""
    return SubscriptionListResponse(
        subscriptions=[subscription_to_schema(s) for s in subs],
        count=len(subs),
        baseline_ref=config.repo.baseline_ref,
        baseline_title=baseline_title,
    )


@app.post("/api/projects/{project_id}/subscriptions", response_model=SubscriptionSchema, status_code=201)
def create_project_subscription(project_id: str, request: SubscriptionCreateRequest):
    """Create a new subscription in a specific project."""
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()

    # Parse and validate location
    path, start_line, end_line = parse_location(request.location)

    # Validate file exists at baseline
    baseline = config.repo.baseline_ref
    lines = repo.show_file(baseline, path)

    # Validate line range
    if end_line > len(lines):
        raise InvalidLineRangeError(
            start_line, end_line, f"exceeds file length ({len(lines)} lines)"
        )

    # Extract anchors
    context_before, watched_lines, context_after = extract_anchors(
        lines, start_line, end_line, context=request.context
    )
    anchors = Anchor(
        context_before=context_before,
        lines=watched_lines,
        context_after=context_after,
    )

    # Create subscription
    sub = Subscription.create(
        path=path,
        start_line=start_line,
        end_line=end_line,
        label=request.label,
        description=request.description,
        anchors=anchors,
    )

    store.add_subscription(sub)
    return subscription_to_schema(sub)


@app.get("/api/projects/{project_id}/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def get_project_subscription(project_id: str, sub_id: str):
    """Get a single subscription by ID within a project."""
    store, _ = get_project_store_and_repo(project_id)
    sub = store.get_subscription(sub_id)
    return subscription_to_schema(sub)


@app.patch("/api/projects/{project_id}/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def update_project_subscription(project_id: str, sub_id: str, request: SubscriptionUpdateRequest):
    """Update subscription label and/or description within a project."""
    store, _ = get_project_store_and_repo(project_id)
    sub = store.get_subscription(sub_id)

    update_data = request.model_dump(exclude_unset=True)

    if "label" in update_data:
        sub.label = request.label if request.label else None
    if "description" in update_data:
        sub.description = request.description if request.description else None

    store.update_subscription(sub)
    return subscription_to_schema(sub)


@app.delete("/api/projects/{project_id}/subscriptions/{sub_id}", response_model=SubscriptionSchema)
def delete_project_subscription(project_id: str, sub_id: str, hard: bool = Query(default=False)):
    """Delete (deactivate or hard delete) a subscription within a project."""
    store, _ = get_project_store_and_repo(project_id)
    sub = store.remove_subscription(sub_id, hard=hard)
    return subscription_to_schema(sub)


@app.post("/api/projects/{project_id}/subscriptions/{sub_id}/reactivate", response_model=SubscriptionSchema)
def reactivate_project_subscription(project_id: str, sub_id: str):
    """Reactivate a deactivated subscription within a project."""
    store, _ = get_project_store_and_repo(project_id)
    sub = store.get_subscription(sub_id)

    if sub.active:
        raise HTTPException(status_code=400, detail="Subscription is already active")

    sub.active = True
    store.update_subscription(sub)
    return subscription_to_schema(sub)


# --- Scan Endpoints ---


@app.post("/api/projects/{project_id}/scan", response_model=ScanHistoryEntrySchema)
def run_project_scan(project_id: str, request: ScanRequest):
    """
    Run a scan for a project and save to history.

    Special ref values:
    - "baseline": Use project's configured baseline ref
    - "HEAD~N": N commits back from HEAD
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()

    # Resolve refs
    base_ref = request.base_ref
    target_ref = request.target_ref

    # Handle special values
    if base_ref == "baseline":
        base_ref = config.repo.baseline_ref

    # Resolve to commit hashes (empty target_ref means working directory)
    base_ref = repo.resolve_ref(base_ref)
    if target_ref:
        target_ref = repo.resolve_ref(target_ref)
    else:
        target_ref = None  # Working directory

    # Run scan
    detector = Detector(repo)
    result = detector.scan(config.subscriptions, base_ref, target_ref)

    # Convert to dict and save to history
    result_dict = result_to_dict(result)
    history = get_scan_history()
    entry = history.save_scan(project_id, result_dict)

    return ScanHistoryEntrySchema(
        id=entry.id,
        project_id=entry.project_id,
        base_ref=entry.base_ref,
        target_ref=entry.target_ref,
        trigger_count=entry.trigger_count,
        proposal_count=entry.proposal_count,
        unchanged_count=entry.unchanged_count,
        created_at=entry.created_at,
    )


@app.get("/api/projects/{project_id}/scan-history", response_model=ScanHistoryListResponse)
def list_scan_history(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100)
):
    """List scan history for a project."""
    # Validate project exists
    project_store = get_project_store()
    _ = project_store.get_project(project_id)

    history = get_scan_history()
    entries = history.list_scans(project_id, limit=limit)

    return ScanHistoryListResponse(
        scans=[
            ScanHistoryEntrySchema(
                id=e.id,
                project_id=e.project_id,
                base_ref=e.base_ref,
                target_ref=e.target_ref,
                trigger_count=e.trigger_count,
                proposal_count=e.proposal_count,
                unchanged_count=e.unchanged_count,
                created_at=e.created_at,
            )
            for e in entries
        ],
        count=len(entries),
    )


@app.get("/api/projects/{project_id}/scan-history/{scan_id}")
def get_scan_result(project_id: str, scan_id: str):
    """Get a specific scan result with full details."""
    # Validate project exists
    project_store = get_project_store()
    _ = project_store.get_project(project_id)

    history = get_scan_history()
    entry = history.get_scan(project_id, scan_id)

    return entry.to_dict()


@app.delete("/api/projects/{project_id}/scan-history")
def clear_project_scan_history(project_id: str):
    """Clear all scan history for a project."""
    # Validate project exists
    project_store = get_project_store()
    _ = project_store.get_project(project_id)

    history = get_scan_history()
    count = history.clear_project_history(project_id)

    return {"deleted": count}


@app.delete("/api/scan-history")
def clear_all_scan_history():
    """Clear all scan history for all projects."""
    history = get_scan_history()
    count = history.clear_all_history()

    return {"deleted": count}


# --- Apply Updates Endpoint ---


@app.post("/api/projects/{project_id}/apply-updates", response_model=ApplyUpdatesResponse)
def apply_project_updates(project_id: str, request: ApplyUpdatesRequest):
    """
    Apply proposals from a scan result.

    Updates subscriptions and advances baseline to the scan's target_ref.
    """
    store, repo = get_project_store_and_repo(project_id)

    # Get the scan result
    history = get_scan_history()
    entry = history.get_scan(project_id, request.scan_id)
    scan_result = entry.scan_result

    # Filter proposals if specific IDs requested
    proposals = scan_result.get("proposals", [])
    if request.proposal_ids:
        proposals = [p for p in proposals if p["subscription_id"] in request.proposal_ids]

    # Build update document format
    update_data = {
        "target_ref": scan_result.get("target_ref", ""),
        "proposals": proposals,
    }

    # Apply updates
    updater = Updater(store, repo)
    applied, warnings = updater.apply(update_data)

    return ApplyUpdatesResponse(
        applied=applied,
        warnings=warnings,
        new_baseline=scan_result.get("target_ref") if applied else None,
    )
