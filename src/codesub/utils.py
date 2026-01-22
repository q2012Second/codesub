"""Utility functions for codesub."""

import re
from pathlib import Path

from .errors import InvalidLocationError, InvalidLineRangeError


def parse_location(location: str) -> tuple[str, int, int]:
    """
    Parse a location spec into (path, start_line, end_line).

    Formats:
    - path/to/file:42 (single line)
    - path/to/file:42-45 (range)

    Returns:
        Tuple of (path, start_line, end_line), all 1-based inclusive.

    Raises:
        InvalidLocationError: If the location format is invalid.
        InvalidLineRangeError: If the line range is invalid.
    """
    # Match path:line or path:start-end
    match = re.match(r"^(.+):(\d+)(?:-(\d+))?$", location)
    if not match:
        raise InvalidLocationError(
            location, "expected format 'path:line' or 'path:start-end'"
        )

    path = match.group(1)
    start = int(match.group(2))
    end = int(match.group(3)) if match.group(3) else start

    if start < 1:
        raise InvalidLineRangeError(start, end, "start line must be >= 1")
    if end < start:
        raise InvalidLineRangeError(start, end, "end line must be >= start line")

    # Normalize path to POSIX style
    path = Path(path).as_posix()

    return path, start, end


def normalize_path(path: str) -> str:
    """Normalize a path to POSIX style (forward slashes)."""
    return Path(path).as_posix()


def extract_anchors(
    lines: list[str], start_line: int, end_line: int, context: int = 2
) -> tuple[list[str], list[str], list[str]]:
    """
    Extract anchor lines from file content.

    Args:
        lines: All lines of the file (0-indexed list).
        start_line: 1-based inclusive start line.
        end_line: 1-based inclusive end line.
        context: Number of context lines before/after.

    Returns:
        Tuple of (context_before, watched_lines, context_after).
    """
    # Convert to 0-based indices
    start_idx = start_line - 1
    end_idx = end_line  # exclusive for slicing

    # Extract watched lines
    watched = lines[start_idx:end_idx]

    # Extract context before
    ctx_before_start = max(0, start_idx - context)
    ctx_before = lines[ctx_before_start:start_idx]

    # Extract context after
    ctx_after_end = min(len(lines), end_idx + context)
    ctx_after = lines[end_idx:ctx_after_end]

    return ctx_before, watched, ctx_after


def format_subscription(sub: "Subscription", verbose: bool = False) -> str:
    """Format a subscription for display."""
    # Import here to avoid circular import
    from .models import Subscription

    status = "active" if sub.active else "inactive"
    label_str = f" [{sub.label}]" if sub.label else ""
    location = f"{sub.path}:{sub.start_line}"
    if sub.end_line != sub.start_line:
        location = f"{sub.path}:{sub.start_line}-{sub.end_line}"

    result = f"{sub.id[:8]}  {location}{label_str} ({status})"

    if verbose:
        if sub.description:
            result += f"\n         Description: {sub.description}"
        if sub.anchors:
            result += "\n         Lines:"
            for line in sub.anchors.lines:
                # Truncate long lines
                display_line = line[:60] + "..." if len(line) > 60 else line
                result += f"\n           | {display_line}"

    return result


def truncate_id(sub_id: str) -> str:
    """Truncate a subscription ID for display."""
    return sub_id[:8]
