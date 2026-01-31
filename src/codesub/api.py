"""FastAPI REST API for codesub subscription management."""

from pathlib import Path
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
    UnsupportedLanguageError,
)
from .git_repo import GitRepo
from .models import Anchor, Subscription, SemanticTarget
from .utils import parse_location, extract_anchors, parse_target_spec, LineTarget, SemanticTargetSpec
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


class MemberFingerprintSchema(BaseModel):
    """Schema for container member fingerprint."""

    kind: str
    interface_hash: str
    body_hash: str


class SemanticTargetSchema(BaseModel):
    """Schema for semantic subscription target."""

    language: str  # "python"
    kind: str  # "variable"|"field"|"method"|"class"|"interface"|"enum"
    qualname: str  # "API_VERSION" | "User.role" | "Calculator.add" | "User"
    role: Optional[str] = None  # "const" for constants, None otherwise
    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1
    # Container tracking fields
    include_members: bool = False
    include_private: bool = False
    track_decorators: bool = True
    baseline_members: Optional[dict[str, MemberFingerprintSchema]] = None
    baseline_container_qualname: Optional[str] = None


class SubscriptionSchema(BaseModel):
    id: str
    path: str
    start_line: int
    end_line: int
    label: Optional[str] = None
    description: Optional[str] = None
    anchors: Optional[AnchorSchema] = None
    semantic: Optional[SemanticTargetSchema] = None
    active: bool = True
    trigger_on_duplicate: bool = False
    created_at: str
    updated_at: str


class SubscriptionCreateRequest(BaseModel):
    """Request body for creating a subscription."""

    location: str = Field(
        ...,
        description="Location format: 'path:line' or 'path:start-end' for line-based, "
        "'path::QualName' or 'path::kind:QualName' for semantic",
    )
    label: Optional[str] = None
    description: Optional[str] = None
    context: int = Field(default=2, ge=0, le=10)
    trigger_on_duplicate: bool = Field(
        default=False,
        description="For semantic subscriptions: trigger alert if construct found in multiple files"
    )
    include_members: bool = Field(
        default=False,
        description="For containers (class/enum): track all members and trigger on any change"
    )
    include_private: bool = Field(
        default=False,
        description="Include private members (_prefixed) when using include_members. Only affects Python."
    )
    track_decorators: bool = Field(
        default=True,
        description="Track decorator changes on the container (when include_members=True)"
    )


class SubscriptionUpdateRequest(BaseModel):
    """Request body for updating a subscription."""

    label: Optional[str] = None
    description: Optional[str] = None
    trigger_on_duplicate: Optional[bool] = None


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
    change_type: Optional[str] = None  # "STRUCTURAL"|"CONTENT"|"MISSING" for semantic subscriptions
    details: Optional[dict] = None  # Additional details for semantic triggers


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
    new_qualname: Optional[str] = None  # For semantic subscriptions when construct renamed
    new_kind: Optional[str] = None  # For semantic subscriptions if kind changed


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


# --- Filesystem Browser Schemas ---


class FilesystemEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class FilesystemBrowseResponse(BaseModel):
    current_path: str
    parent_path: Optional[str]
    entries: list[FilesystemEntry]


# --- Code Browser Schemas ---


class FileEntry(BaseModel):
    """A file in the repository."""
    path: str  # Repo-relative path (e.g., "src/codesub/api.py")
    name: str  # Filename only (e.g., "api.py")
    extension: str  # File extension (e.g., ".py")


class FileListResponse(BaseModel):
    """Response for file listing."""
    files: list[FileEntry]
    total: int
    has_more: bool


class FileContentResponse(BaseModel):
    """Response for file content."""
    path: str
    total_lines: int
    lines: list[str]  # Line contents (frontend adds line numbers)
    language: Optional[str] = None
    supports_semantic: bool = False
    truncated: bool = False


class ConstructSchema(BaseModel):
    """A semantic construct in the file."""
    kind: str
    qualname: str
    role: Optional[str] = None
    start_line: int
    end_line: int
    definition_line: int  # Line of actual definition (differs from start_line if decorated)
    target: str  # Ready-to-use location string


class SymbolsResponse(BaseModel):
    """Response for file symbols."""
    path: str
    language: str
    constructs: list[ConstructSchema]
    has_parse_error: bool = False
    error_message: Optional[str] = None


# --- Code Browser Cache ---

# Cache file lists per (project_id, baseline_ref) for 60 seconds
_file_list_cache: dict[tuple[str, str], tuple[list[str], float]] = {}
_FILE_LIST_CACHE_TTL = 60.0

# Common code/text file extensions
TEXT_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".clj",
    ".html", ".css", ".scss", ".sass", ".less", ".json", ".yaml", ".yml",
    ".xml", ".toml", ".ini", ".cfg", ".conf", ".md", ".txt", ".rst", ".sql",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
    ".dockerfile", ".vue", ".svelte", ".astro", ".prisma", ".graphql",
}


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
    store = ConfigStore(project_id)  # Use project_id, not repo.root
    store.set_repo_root(repo.root)   # Set repo root for migration/operations
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
    semantic = None
    if sub.semantic:
        # Convert baseline_members if present
        baseline_members = None
        if sub.semantic.baseline_members:
            baseline_members = {
                k: MemberFingerprintSchema(
                    kind=v.kind,
                    interface_hash=v.interface_hash,
                    body_hash=v.body_hash,
                )
                for k, v in sub.semantic.baseline_members.items()
            }

        semantic = SemanticTargetSchema(
            language=sub.semantic.language,
            kind=sub.semantic.kind,
            qualname=sub.semantic.qualname,
            role=sub.semantic.role,
            interface_hash=sub.semantic.interface_hash,
            body_hash=sub.semantic.body_hash,
            fingerprint_version=sub.semantic.fingerprint_version,
            include_members=sub.semantic.include_members,
            include_private=sub.semantic.include_private,
            track_decorators=sub.semantic.track_decorators,
            baseline_members=baseline_members,
            baseline_container_qualname=sub.semantic.baseline_container_qualname,
        )
    return SubscriptionSchema(
        id=sub.id,
        path=sub.path,
        start_line=sub.start_line,
        end_line=sub.end_line,
        label=sub.label,
        description=sub.description,
        anchors=anchors,
        semantic=semantic,
        active=sub.active,
        trigger_on_duplicate=sub.trigger_on_duplicate,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def _create_subscription_from_request(
    store: ConfigStore,
    repo: GitRepo,
    baseline: str,
    request: SubscriptionCreateRequest,
) -> Subscription:
    """Create a subscription from a request, handling both line-based and semantic targets."""
    from .semantic import get_indexer_for_path

    target = parse_target_spec(request.location)

    if isinstance(target, SemanticTargetSpec):
        # Semantic subscription
        from .models import CONTAINER_KINDS, MemberFingerprint

        lines = repo.show_file(baseline, target.path)
        source = "\n".join(lines)

        language, indexer = get_indexer_for_path(target.path)
        construct = indexer.find_construct(
            source, target.path, target.qualname, target.kind
        )
        if construct is None:
            raise InvalidLocationError(
                request.location,
                f"Construct '{target.qualname}' not found. Use 'codesub symbols' to discover valid targets.",
            )

        # Handle container tracking flags
        include_members = request.include_members
        include_private = request.include_private
        track_decorators = request.track_decorators
        baseline_members = None
        baseline_container_qualname = None

        if include_members:
            # Validate container kind
            valid_kinds = CONTAINER_KINDS.get(language, set())
            if construct.kind not in valid_kinds:
                raise InvalidLocationError(
                    request.location,
                    f"--include-members only valid for: {', '.join(sorted(valid_kinds))}. "
                    f"'{construct.qualname}' is a {construct.kind}.",
                )

            # Store baseline container qualname
            baseline_container_qualname = construct.qualname

            # Index file once and capture member fingerprints with relative IDs
            all_constructs = indexer.index_file(source, target.path)
            members = indexer.get_container_members(
                source, target.path, construct.qualname, include_private,
                constructs=all_constructs
            )
            baseline_members = {}
            for m in members:
                # Store by relative member ID
                relative_id = m.qualname[len(construct.qualname) + 1:]
                baseline_members[relative_id] = MemberFingerprint(
                    kind=m.kind,
                    interface_hash=m.interface_hash,
                    body_hash=m.body_hash,
                )

        # Extract anchors from construct lines
        context_before, watched_lines, context_after = extract_anchors(
            lines, construct.start_line, construct.end_line, context=request.context
        )
        anchors = Anchor(
            context_before=context_before,
            lines=watched_lines,
            context_after=context_after,
        )

        # Create semantic target with container flags
        semantic = SemanticTarget(
            language=language,
            kind=construct.kind,
            qualname=construct.qualname,
            role=construct.role,
            interface_hash=construct.interface_hash,
            body_hash=construct.body_hash,
            include_members=include_members,
            include_private=include_private,
            track_decorators=track_decorators,
            baseline_members=baseline_members,
            baseline_container_qualname=baseline_container_qualname,
        )

        return Subscription.create(
            path=target.path,
            start_line=construct.start_line,
            end_line=construct.end_line,
            label=request.label,
            description=request.description,
            anchors=anchors,
            semantic=semantic,
            trigger_on_duplicate=request.trigger_on_duplicate,
        )
    else:
        # Line-based subscription
        lines = repo.show_file(baseline, target.path)

        # Validate line range
        if target.end_line > len(lines):
            raise InvalidLineRangeError(
                target.start_line,
                target.end_line,
                f"exceeds file length ({len(lines)} lines)",
            )

        # Extract anchors
        context_before, watched_lines, context_after = extract_anchors(
            lines, target.start_line, target.end_line, context=request.context
        )
        anchors = Anchor(
            context_before=context_before,
            lines=watched_lines,
            context_after=context_after,
        )

        return Subscription.create(
            path=target.path,
            start_line=target.start_line,
            end_line=target.end_line,
            label=request.label,
            description=request.description,
            anchors=anchors,
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
    UnsupportedLanguageError: 400,
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


@app.get("/api/health")
def health_check():
    """
    Health check endpoint.

    Returns basic service status. Project-agnostic.
    """
    project_store = get_project_store()
    try:
        projects = project_store.list_projects()
        return {
            "status": "ok",
            "project_count": len(projects),
        }
    except Exception as e:
        return {
            "status": "error",
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
def delete_project(project_id: str, keep_data: bool = Query(default=False)):
    """
    Remove a project from the registry.

    By default, deletes subscription and scan history data.
    Use keep_data=true to preserve the data.
    """
    store = get_project_store()
    project = store.remove_project(project_id, keep_data=keep_data)
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
    """Create a new subscription in a specific project (line-based or semantic)."""
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    sub = _create_subscription_from_request(store, repo, baseline, request)
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
    if "trigger_on_duplicate" in update_data:
        sub.trigger_on_duplicate = request.trigger_on_duplicate

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


# --- Filesystem Browser Endpoint ---


@app.get("/api/filesystem/browse", response_model=FilesystemBrowseResponse)
def browse_filesystem(path: str = Query(default="~", description="Path to browse")):
    """
    Browse filesystem directories.

    Used by the frontend to provide a file picker for selecting project paths.
    Returns directories (not files) sorted alphabetically, with hidden dirs excluded.
    Restricted to user's home directory for security.
    """
    home = Path.home().resolve()

    # Expand ~ and resolve path
    try:
        expanded = Path(path).expanduser().resolve()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid path: {path}")

    # Security: restrict to home directory
    try:
        expanded.relative_to(home)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Access restricted to home directory ({home})"
        )

    if not expanded.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    if not expanded.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    # Get parent path (None if at home directory)
    if expanded == home:
        parent_path = None
    else:
        parent = expanded.parent
        # Ensure parent is still within home
        try:
            parent.relative_to(home)
            parent_path = str(parent)
        except ValueError:
            parent_path = None

    # List directory entries (directories only, exclude hidden)
    entries: list[FilesystemEntry] = []
    try:
        for item in sorted(expanded.iterdir(), key=lambda p: p.name.lower()):
            try:
                # Skip hidden directories
                if item.name.startswith("."):
                    continue
                # Skip symlinks to avoid escaping home directory
                if item.is_symlink():
                    continue
                if item.is_dir():
                    entries.append(
                        FilesystemEntry(
                            name=item.name,
                            path=str(item),
                            is_dir=True,
                        )
                    )
            except OSError:
                # Skip entries that can't be inspected (broken symlinks, etc.)
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    return FilesystemBrowseResponse(
        current_path=str(expanded),
        parent_path=parent_path,
        entries=entries,
    )


# --- Code Browser Endpoints ---


def _get_cached_file_list(project_id: str, baseline: str, repo: GitRepo) -> list[str]:
    """Get file list from cache or fetch from git."""
    from time import time
    cache_key = (project_id, baseline)
    now = time()

    if cache_key in _file_list_cache:
        files, cached_at = _file_list_cache[cache_key]
        if now - cached_at < _FILE_LIST_CACHE_TTL:
            return files

    files = repo.list_files(baseline)
    _file_list_cache[cache_key] = (files, now)
    return files


MAX_FILE_LINES = 5000  # Hard limit for browser display


@app.get("/api/projects/{project_id}/files", response_model=FileListResponse)
def list_project_files(
    project_id: str,
    search: Optional[str] = Query(None, description="Filter by path substring"),
    extensions: Optional[str] = Query(None, description="Comma-separated extensions (e.g., '.py,.java')"),
    text_only: bool = Query(default=True, description="Only show common text/code files"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List git-tracked files in a project at the baseline ref.

    By default, filters to common code/text file extensions.
    Results are sorted alphabetically by path.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get cached file list
    files = _get_cached_file_list(project_id, baseline, repo)

    # Apply text_only filter (default)
    if text_only and not extensions:
        files = [f for f in files if Path(f).suffix.lower() in TEXT_EXTENSIONS]

    # Apply extension filter if specified
    if extensions:
        ext_list = [e.strip().lower() for e in extensions.split(",")]
        ext_list = ["." + e if not e.startswith(".") else e for e in ext_list]
        files = [f for f in files if Path(f).suffix.lower() in ext_list]

    # Apply search filter
    if search:
        search_lower = search.lower()
        files = [f for f in files if search_lower in f.lower()]

    # Sort and paginate
    files.sort()
    total = len(files)
    paginated = files[offset:offset + limit]

    return FileListResponse(
        files=[
            FileEntry(
                path=f,
                name=Path(f).name,
                extension=Path(f).suffix.lower(),
            )
            for f in paginated
        ],
        total=total,
        has_more=(offset + len(paginated)) < total,
    )


@app.get("/api/projects/{project_id}/file-content", response_model=FileContentResponse)
def get_project_file_content(
    project_id: str,
    path: str = Query(..., description="Repo-relative file path"),
):
    """
    Get file content at the project's baseline ref.

    Returns up to 5000 lines. Files larger than this are truncated with a warning.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get file content
    try:
        all_lines = repo.show_file(baseline, path)
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=415,
            detail=f"Cannot display binary or non-UTF8 file: {path}"
        )

    total_lines = len(all_lines)
    truncated = total_lines > MAX_FILE_LINES
    lines = all_lines[:MAX_FILE_LINES] if truncated else all_lines

    # Detect language support
    from .semantic import get_indexer_for_path
    language = None
    supports_semantic = False
    try:
        language, _ = get_indexer_for_path(path)
        supports_semantic = True
    except UnsupportedLanguageError:
        pass

    return FileContentResponse(
        path=path,
        total_lines=total_lines,
        lines=lines,
        language=language,
        supports_semantic=supports_semantic,
        truncated=truncated,
    )


@app.get("/api/projects/{project_id}/file-symbols", response_model=SymbolsResponse)
def get_project_file_symbols(
    project_id: str,
    path: str = Query(..., description="Repo-relative file path"),
    kind: Optional[str] = Query(None, description="Filter by construct kind"),
):
    """
    Get semantic constructs in a file.

    Only works for supported languages (Python, Java).
    Returns all discoverable constructs with their line ranges.
    """
    store, repo = get_project_store_and_repo(project_id)
    config = store.load()
    baseline = config.repo.baseline_ref

    # Get file content
    lines = repo.show_file(baseline, path)
    source = "\n".join(lines)

    # Get indexer
    from .semantic import get_indexer_for_path
    language, indexer = get_indexer_for_path(path)

    # Index file with error handling
    try:
        constructs = indexer.index_file(source, path)
    except Exception as e:
        return SymbolsResponse(
            path=path,
            language=language,
            constructs=[],
            has_parse_error=True,
            error_message=f"Failed to parse file: {e}",
        )

    # Filter by kind if specified
    if kind:
        constructs = [c for c in constructs if c.kind == kind]

    # Check for parse errors in constructs
    has_parse_error = any(c.has_parse_error for c in constructs)

    return SymbolsResponse(
        path=path,
        language=language,
        constructs=[
            ConstructSchema(
                kind=c.kind,
                qualname=c.qualname,
                role=c.role,
                start_line=c.start_line,
                end_line=c.end_line,
                definition_line=c.definition_line,
                target=f"{path}::{c.kind}:{c.qualname}",
            )
            for c in constructs
        ],
        has_parse_error=has_parse_error,
    )
