"""Scan history storage for codesub."""

import json
import os
from pathlib import Path
from typing import Any

from .errors import ScanNotFoundError
from .models import ScanHistoryEntry, _generate_id, _utc_now

# Local data directory within the codesub project
# Can be overridden via CODESUB_DATA_DIR environment variable
_default_data_dir = Path(__file__).parent.parent.parent / "data"
DATA_DIR = Path(os.environ.get("CODESUB_DATA_DIR", _default_data_dir))
SCAN_HISTORY_DIR = "scan_history"


class ScanHistory:
    """Manages scan history storage and retrieval."""

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize ScanHistory.

        Args:
            config_dir: Override config directory (for testing).
        """
        self.config_dir = config_dir or DATA_DIR
        self.history_dir = self.config_dir / SCAN_HISTORY_DIR

    def _project_dir(self, project_id: str) -> Path:
        """Get the history directory for a project."""
        return self.history_dir / project_id

    def _ensure_dir(self, project_id: str) -> Path:
        """Ensure project history directory exists."""
        path = self._project_dir(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_scan(
        self,
        project_id: str,
        scan_result: dict[str, Any],
    ) -> ScanHistoryEntry:
        """
        Save a scan result to history.

        Args:
            project_id: Project ID.
            scan_result: Scan result dict (from result_to_dict).

        Returns:
            The created ScanHistoryEntry.
        """
        scan_id = _generate_id()
        now = _utc_now()

        entry = ScanHistoryEntry(
            id=scan_id,
            project_id=project_id,
            base_ref=scan_result.get("base_ref", ""),
            target_ref=scan_result.get("target_ref", ""),
            trigger_count=len(scan_result.get("triggers", [])),
            proposal_count=len(scan_result.get("proposals", [])),
            unchanged_count=len(scan_result.get("unchanged", [])),
            created_at=now,
            scan_result=scan_result,
        )

        # Save to file
        project_dir = self._ensure_dir(project_id)
        filename = f"{scan_id}.json"
        file_path = project_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2)
            f.write("\n")

        return entry

    def list_scans(
        self,
        project_id: str,
        limit: int | None = None,
    ) -> list[ScanHistoryEntry]:
        """
        List scan history for a project.

        Args:
            project_id: Project ID.
            limit: Maximum number of entries to return (newest first).

        Returns:
            List of ScanHistoryEntry, sorted by created_at descending.
        """
        project_dir = self._project_dir(project_id)

        if not project_dir.exists():
            return []

        entries: list[ScanHistoryEntry] = []

        for file_path in project_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries.append(ScanHistoryEntry.from_dict(data))
            except Exception:
                continue  # Skip corrupted files

        # Sort by created_at descending
        entries.sort(key=lambda e: e.created_at, reverse=True)

        if limit:
            entries = entries[:limit]

        return entries

    def get_scan(self, project_id: str, scan_id: str) -> ScanHistoryEntry:
        """
        Get a specific scan result.

        Args:
            project_id: Project ID.
            scan_id: Scan ID.

        Returns:
            The ScanHistoryEntry.

        Raises:
            ScanNotFoundError: If scan doesn't exist.
        """
        project_dir = self._project_dir(project_id)
        file_path = project_dir / f"{scan_id}.json"

        if not file_path.exists():
            raise ScanNotFoundError(scan_id)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ScanHistoryEntry.from_dict(data)

    def clear_project_history(self, project_id: str) -> int:
        """
        Clear all scan history for a project.

        Args:
            project_id: Project ID.

        Returns:
            Number of entries deleted.
        """
        project_dir = self._project_dir(project_id)

        if not project_dir.exists():
            return 0

        count = 0
        for file_path in project_dir.glob("*.json"):
            try:
                file_path.unlink()
                count += 1
            except Exception:
                pass

        # Try to remove the directory
        try:
            project_dir.rmdir()
        except Exception:
            pass

        return count

    def clear_all_history(self) -> int:
        """
        Clear all scan history for all projects.

        Returns:
            Total number of entries deleted.
        """
        if not self.history_dir.exists():
            return 0

        count = 0
        for project_dir in self.history_dir.iterdir():
            if project_dir.is_dir():
                for file_path in project_dir.glob("*.json"):
                    try:
                        file_path.unlink()
                        count += 1
                    except Exception:
                        pass
                try:
                    project_dir.rmdir()
                except Exception:
                    pass

        return count
