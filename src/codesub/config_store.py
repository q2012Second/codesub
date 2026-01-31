"""Configuration storage for codesub."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from .errors import (
    ConfigExistsError,
    ConfigNotFoundError,
    InvalidSchemaVersionError,
    SubscriptionNotFoundError,
)
from .models import Config, Subscription, _utc_now

import os

SCHEMA_VERSION = 1

# Centralized storage constants
# Can be overridden via CODESUB_DATA_DIR environment variable
_default_data_dir = Path(__file__).parent.parent.parent / "data"
DATA_DIR = Path(os.environ.get("CODESUB_DATA_DIR", _default_data_dir))
SUBSCRIPTIONS_DIR = "subscriptions"
CONFIG_FILE = "subscriptions.json"
UPDATE_DOCS_DIR = "last_update_docs"

# Legacy storage constants (for migration)
LEGACY_CONFIG_DIR = ".codesub"


class ConfigStore:
    """Manages reading and writing the subscription configuration."""

    def __init__(self, project_id: str, config_dir: Path | None = None):
        """
        Initialize ConfigStore.

        Args:
            project_id: The project ID (used as storage key).
            config_dir: Override base config directory (for testing).
        """
        self.project_id = project_id
        self._base_dir = config_dir or DATA_DIR
        self.config_dir = self._base_dir / SUBSCRIPTIONS_DIR / project_id
        self.config_path = self.config_dir / CONFIG_FILE
        self.update_docs_dir = self.config_dir / UPDATE_DOCS_DIR
        self._repo_root: Path | None = None

    def set_repo_root(self, repo_root: Path) -> None:
        """
        Set repo root for migration and path operations.

        This triggers auto-migration from legacy .codesub/ location if needed.
        """
        self._repo_root = repo_root
        self._try_migrate(repo_root)

    def _get_legacy_path(self, repo_root: Path) -> Path:
        """Get legacy .codesub config path for migration."""
        return repo_root / LEGACY_CONFIG_DIR / CONFIG_FILE

    def _try_migrate(self, repo_root: Path) -> bool:
        """
        Attempt to migrate from legacy .codesub/ location.

        Returns True if migration occurred, False otherwise.
        """
        if self.config_path.exists():
            return False  # Already migrated or initialized

        legacy_path = self._get_legacy_path(repo_root)
        if not legacy_path.exists():
            return False  # No legacy config to migrate

        # Perform migration
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Copy config file
        shutil.copy2(legacy_path, self.config_path)

        # Copy update_docs if present
        legacy_docs = legacy_path.parent / UPDATE_DOCS_DIR
        if legacy_docs.exists():
            shutil.copytree(legacy_docs, self.update_docs_dir, dirs_exist_ok=True)

        return True

    def exists(self) -> bool:
        """Check if config file exists."""
        return self.config_path.exists()

    def load(self) -> Config:
        """
        Load configuration from disk.

        Raises:
            ConfigNotFoundError: If config doesn't exist.
            InvalidSchemaVersionError: If schema version is unsupported.
        """
        if not self.exists():
            raise ConfigNotFoundError(str(self.config_path))

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("schema_version", 0)
        if version != SCHEMA_VERSION:
            raise InvalidSchemaVersionError(version, SCHEMA_VERSION)

        return Config.from_dict(data)

    def save(self, config: Config) -> None:
        """
        Save configuration to disk atomically.

        Uses write-to-temp-then-rename for atomicity.
        """
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Update the updated_at timestamp
        config.repo.updated_at = _utc_now()

        # Write to temp file then rename (atomic on POSIX)
        data = config.to_dict()
        fd, temp_path = tempfile.mkstemp(
            dir=self.config_dir, prefix=".subscriptions_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")  # trailing newline
            os.replace(temp_path, self.config_path)
        except Exception:
            # Clean up temp file on failure (ignore errors if already removed)
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def init(self, baseline_ref: str, force: bool = False) -> Config:
        """
        Initialize a new configuration.

        Called automatically when a project is registered.

        Args:
            baseline_ref: The baseline git ref (usually HEAD).
            force: If True, overwrite existing config.

        Returns:
            The created Config.

        Raises:
            ConfigExistsError: If config exists and force=False.
        """
        if self.exists() and not force:
            raise ConfigExistsError(str(self.config_path))

        config = Config.create(baseline_ref)
        self.save(config)

        # Create update docs directory
        self.update_docs_dir.mkdir(parents=True, exist_ok=True)

        return config

    def add_subscription(self, sub: Subscription) -> None:
        """Add a subscription to the config."""
        config = self.load()
        config.subscriptions.append(sub)
        self.save(config)

    def list_subscriptions(self, include_inactive: bool = False) -> list[Subscription]:
        """
        List all subscriptions.

        Args:
            include_inactive: If True, include inactive subscriptions.
        """
        config = self.load()
        if include_inactive:
            return config.subscriptions
        return [s for s in config.subscriptions if s.active]

    def get_subscription(self, sub_id: str) -> Subscription:
        """
        Get a subscription by ID (supports partial ID matching).

        Raises:
            SubscriptionNotFoundError: If subscription doesn't exist.
        """
        config = self.load()
        matches = [s for s in config.subscriptions if s.id.startswith(sub_id)]

        if not matches:
            raise SubscriptionNotFoundError(sub_id)
        if len(matches) > 1:
            raise SubscriptionNotFoundError(
                f"{sub_id} (ambiguous, matches {len(matches)} subscriptions)"
            )

        return matches[0]

    def remove_subscription(self, sub_id: str, hard: bool = False) -> Subscription:
        """
        Remove or deactivate a subscription.

        Args:
            sub_id: Subscription ID (or prefix).
            hard: If True, delete entirely. If False, set active=False.

        Returns:
            The removed/deactivated subscription.

        Raises:
            SubscriptionNotFoundError: If subscription doesn't exist.
        """
        config = self.load()
        matches = [(i, s) for i, s in enumerate(config.subscriptions) if s.id.startswith(sub_id)]

        if not matches:
            raise SubscriptionNotFoundError(sub_id)
        if len(matches) > 1:
            raise SubscriptionNotFoundError(
                f"{sub_id} (ambiguous, matches {len(matches)} subscriptions)"
            )

        idx, sub = matches[0]

        if hard:
            config.subscriptions.pop(idx)
        else:
            sub.active = False
            sub.updated_at = _utc_now()

        self.save(config)
        return sub

    def update_subscription(self, sub: Subscription) -> None:
        """
        Update an existing subscription.

        Raises:
            SubscriptionNotFoundError: If subscription doesn't exist.
        """
        config = self.load()
        for i, existing in enumerate(config.subscriptions):
            if existing.id == sub.id:
                sub.updated_at = _utc_now()
                config.subscriptions[i] = sub
                self.save(config)
                return

        raise SubscriptionNotFoundError(sub.id)

    def update_baseline(self, new_ref: str) -> None:
        """Update the baseline ref."""
        config = self.load()
        config.repo.baseline_ref = new_ref
        self.save(config)

    def get_baseline(self) -> str:
        """Get the current baseline ref."""
        config = self.load()
        return config.repo.baseline_ref
