"""Data models for codesub."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    """Generate a new subscription ID."""
    return str(uuid.uuid4())


@dataclass
class Anchor:
    """Context lines around a subscription for display and future fuzzy matching."""

    context_before: list[str]
    lines: list[str]
    context_after: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_before": self.context_before,
            "lines": self.lines,
            "context_after": self.context_after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Anchor":
        return cls(
            context_before=data.get("context_before", []),
            lines=data.get("lines", []),
            context_after=data.get("context_after", []),
        )


@dataclass
class Subscription:
    """A subscription to a file line range."""

    id: str
    path: str  # repo-relative, POSIX-style
    start_line: int  # 1-based inclusive
    end_line: int  # 1-based inclusive
    label: str | None = None
    description: str | None = None
    anchors: Anchor | None = None
    active: bool = True
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "active": self.active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.label is not None:
            result["label"] = self.label
        if self.description is not None:
            result["description"] = self.description
        if self.anchors is not None:
            result["anchors"] = self.anchors.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Subscription":
        anchors = None
        if "anchors" in data:
            anchors = Anchor.from_dict(data["anchors"])
        return cls(
            id=data["id"],
            path=data["path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            label=data.get("label"),
            description=data.get("description"),
            anchors=anchors,
            active=data.get("active", True),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    @classmethod
    def create(
        cls,
        path: str,
        start_line: int,
        end_line: int,
        label: str | None = None,
        description: str | None = None,
        anchors: Anchor | None = None,
    ) -> "Subscription":
        """Create a new subscription with generated ID and timestamps."""
        now = _utc_now()
        return cls(
            id=_generate_id(),
            path=path,
            start_line=start_line,
            end_line=end_line,
            label=label,
            description=description,
            anchors=anchors,
            active=True,
            created_at=now,
            updated_at=now,
        )


@dataclass
class RepoConfig:
    """Repository-level configuration."""

    baseline_ref: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_ref": self.baseline_ref,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepoConfig":
        return cls(
            baseline_ref=data["baseline_ref"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class Config:
    """Full configuration containing repo config and subscriptions."""

    schema_version: int
    repo: RepoConfig
    subscriptions: list[Subscription]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo": self.repo.to_dict(),
            "subscriptions": [s.to_dict() for s in self.subscriptions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            schema_version=data["schema_version"],
            repo=RepoConfig.from_dict(data["repo"]),
            subscriptions=[Subscription.from_dict(s) for s in data.get("subscriptions", [])],
        )

    @classmethod
    def create(cls, baseline_ref: str) -> "Config":
        """Create a new config with the given baseline ref."""
        return cls(
            schema_version=1,
            repo=RepoConfig(baseline_ref=baseline_ref),
            subscriptions=[],
        )


# Models for diff parsing


@dataclass
class Hunk:
    """A single hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int


@dataclass
class FileDiff:
    """Diff information for a single file."""

    old_path: str
    new_path: str
    hunks: list[Hunk]
    is_rename: bool = False
    is_new_file: bool = False
    is_deleted_file: bool = False


# Models for detection results


@dataclass
class Trigger:
    """A subscription that was triggered by changes."""

    subscription_id: str
    subscription: Subscription
    path: str
    start_line: int
    end_line: int
    reasons: list[str]  # e.g., ["overlap_hunk", "file_deleted", "insert_inside_range"]
    matching_hunks: list[Hunk]


@dataclass
class Proposal:
    """A proposed update to a subscription (rename or line shift)."""

    subscription_id: str
    subscription: Subscription
    old_path: str
    old_start: int
    old_end: int
    new_path: str
    new_start: int
    new_end: int
    reasons: list[str]  # ["rename", "line_shift"]
    confidence: str = "high"  # "high" for POC (math-based)
    shift: int | None = None


@dataclass
class ScanResult:
    """Result of scanning for changes."""

    base_ref: str
    target_ref: str
    triggers: list[Trigger]
    proposals: list[Proposal]
    unchanged: list[Subscription]  # Subscriptions with no changes or shifts
