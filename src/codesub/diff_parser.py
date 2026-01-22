"""Git diff parsing for codesub."""

import re
from dataclasses import dataclass, field

from .models import FileDiff, Hunk


# Regex patterns
HUNK_PATTERN = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
DIFF_HEADER_PATTERN = re.compile(r"^diff --git a/(.+) b/(.+)$")
NEW_FILE_PATTERN = re.compile(r"^new file mode")
DELETED_FILE_PATTERN = re.compile(r"^deleted file mode")
RENAME_FROM_PATTERN = re.compile(r"^rename from (.+)$")
RENAME_TO_PATTERN = re.compile(r"^rename to (.+)$")


class DiffParser:
    """Parser for git unified diff output."""

    def parse_patch(self, diff_text: str) -> list[FileDiff]:
        """
        Parse a unified diff into structured FileDiff objects.

        Args:
            diff_text: Output from `git diff -U0 --find-renames base target`.

        Returns:
            List of FileDiff objects, one per changed file.
        """
        if not diff_text.strip():
            return []

        file_diffs: list[FileDiff] = []
        current_diff: FileDiff | None = None
        lines = diff_text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for diff header
            header_match = DIFF_HEADER_PATTERN.match(line)
            if header_match:
                # Save previous diff if exists
                if current_diff is not None:
                    # Sort hunks by old_start before appending
                    current_diff.hunks.sort(key=lambda h: h.old_start)
                    file_diffs.append(current_diff)

                old_path = header_match.group(1)
                new_path = header_match.group(2)
                current_diff = FileDiff(
                    old_path=old_path,
                    new_path=new_path,
                    hunks=[],
                )
                i += 1
                continue

            # Check for file mode indicators
            if current_diff is not None:
                if NEW_FILE_PATTERN.match(line):
                    current_diff.is_new_file = True
                    i += 1
                    continue

                if DELETED_FILE_PATTERN.match(line):
                    current_diff.is_deleted_file = True
                    i += 1
                    continue

                rename_from = RENAME_FROM_PATTERN.match(line)
                if rename_from:
                    current_diff.old_path = rename_from.group(1)
                    current_diff.is_rename = True
                    i += 1
                    continue

                rename_to = RENAME_TO_PATTERN.match(line)
                if rename_to:
                    current_diff.new_path = rename_to.group(1)
                    current_diff.is_rename = True
                    i += 1
                    continue

            # Check for hunk header
            hunk_match = HUNK_PATTERN.match(line)
            if hunk_match and current_diff is not None:
                old_start = int(hunk_match.group(1))
                old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
                new_start = int(hunk_match.group(3))
                new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1

                # Special case: when old_count is 0, old_start indicates
                # the line after which insertion happens
                # When new_count is 0, it's a pure deletion

                hunk = Hunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                )
                current_diff.hunks.append(hunk)

            i += 1

        # Don't forget the last file
        if current_diff is not None:
            current_diff.hunks.sort(key=lambda h: h.old_start)
            file_diffs.append(current_diff)

        return file_diffs

    def parse_name_status(self, name_status_text: str) -> tuple[dict[str, str], dict[str, str]]:
        """
        Parse git diff --name-status output.

        Args:
            name_status_text: Output from `git diff --name-status -M --find-renames base target`.

        Returns:
            Tuple of (rename_map, status_map):
            - rename_map: {old_path: new_path} for renamed files
            - status_map: {path: status} where status is M/A/D/R etc.
        """
        rename_map: dict[str, str] = {}
        status_map: dict[str, str] = {}

        if not name_status_text.strip():
            return rename_map, status_map

        for line in name_status_text.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0]
            if status.startswith("R"):
                # Rename: R100\told_path\tnew_path
                if len(parts) >= 3:
                    old_path = parts[1]
                    new_path = parts[2]
                    rename_map[old_path] = new_path
                    status_map[old_path] = status
            else:
                # Other status: M/A/D\tpath
                path = parts[1]
                status_map[path] = status

        return rename_map, status_map


def ranges_overlap(start1: int, end1: int, start2: int, end2: int) -> bool:
    """
    Check if two ranges overlap (inclusive on both ends).

    Args:
        start1, end1: First range (inclusive).
        start2, end2: Second range (inclusive).

    Returns:
        True if ranges overlap.
    """
    return max(start1, start2) <= min(end1, end2)
