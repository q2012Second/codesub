"""Configuration storage for codesub."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import (
    ConfigExistsError,
    ConfigNotFoundError,
    InvalidSchemaVersionError,
    SubscriptionNotFoundError,
)
from .models import Config, Subscription, _utc_now

SCHEMA_VERSION = 1
CONFIG_DIR = ".codesub"
CONFIG_FILE = "subscriptions.json"
UPDATE_DOCS_DIR = "last_update_docs"


class ConfigStore:
    """Manages reading and writing the subscription configuration."""

    def __init__(self, repo_root: Path):
        """
        Initialize ConfigStore.

        Args:
            repo_root: Path to the repository root directory.
        """
        self.repo_root = repo_root
        self.config_dir = repo_root / CONFIG_DIR
        self.config_path = self.config_dir / CONFIG_FILE
        self.update_docs_dir = self.config_dir / UPDATE_DOCS_DIR

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
