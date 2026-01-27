"""Update document generation for codesub."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Proposal, ScanResult, Trigger


def result_to_dict(result: ScanResult) -> dict[str, Any]:
    """
    Convert a ScanResult to a dictionary for JSON serialization.

    Args:
        result: The scan result.

    Returns:
        Dictionary representation.
    """
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "base_ref": result.base_ref,
        "target_ref": result.target_ref,
        "triggers": [_trigger_to_dict(t) for t in result.triggers],
        "proposals": [_proposal_to_dict(p) for p in result.proposals],
    }


def _trigger_to_dict(trigger: Trigger) -> dict[str, Any]:
    """Convert a Trigger to a dictionary."""
    result = {
        "subscription_id": trigger.subscription_id,
        "path": trigger.path,
        "start_line": trigger.start_line,
        "end_line": trigger.end_line,
        "reasons": trigger.reasons,
        "label": trigger.subscription.label,
        "matching_hunks": [
            {
                "old_start": h.old_start,
                "old_count": h.old_count,
                "new_start": h.new_start,
                "new_count": h.new_count,
            }
            for h in trigger.matching_hunks
        ],
    }
    # Add semantic-specific fields if present
    if trigger.change_type is not None:
        result["change_type"] = trigger.change_type
    if trigger.details is not None:
        result["details"] = trigger.details
    return result


def _proposal_to_dict(proposal: Proposal) -> dict[str, Any]:
    """Convert a Proposal to a dictionary."""
    result = {
        "subscription_id": proposal.subscription_id,
        "old_path": proposal.old_path,
        "old_start": proposal.old_start,
        "old_end": proposal.old_end,
        "new_path": proposal.new_path,
        "new_start": proposal.new_start,
        "new_end": proposal.new_end,
        "reasons": proposal.reasons,
        "confidence": proposal.confidence,
        "shift": proposal.shift,
        "label": proposal.subscription.label,
    }
    # Add semantic-specific fields if present
    if proposal.new_qualname is not None:
        result["new_qualname"] = proposal.new_qualname
    if proposal.new_kind is not None:
        result["new_kind"] = proposal.new_kind
    return result


def write_update_doc(result: ScanResult, path: str | Path) -> None:
    """
    Write a JSON update document.

    Args:
        result: The scan result.
        path: Path to write the document.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = result_to_dict(result)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def write_markdown_doc(result: ScanResult, path: str | Path) -> None:
    """
    Write a human-readable markdown summary.

    Args:
        result: The scan result.
        path: Path to write the document.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Code Subscription Scan Report",
        "",
        f"**Base:** `{result.base_ref[:12]}`",
        f"**Target:** `{result.target_ref[:12]}`",
        f"**Generated:** {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "",
    ]

    # Summary
    lines.extend([
        "## Summary",
        "",
        f"- **Triggered:** {len(result.triggers)}",
        f"- **Proposed Updates:** {len(result.proposals)}",
        f"- **Unchanged:** {len(result.unchanged)}",
        "",
    ])

    # Triggered subscriptions
    if result.triggers:
        lines.extend([
            "## Triggered Subscriptions",
            "",
            "These subscriptions were triggered because the watched lines were modified:",
            "",
        ])

        for trigger in result.triggers:
            label = f" ({trigger.subscription.label})" if trigger.subscription.label else ""
            location = f"{trigger.path}:{trigger.start_line}-{trigger.end_line}"
            reasons = ", ".join(trigger.reasons)
            lines.extend([
                f"### `{trigger.subscription_id[:8]}`{label}",
                "",
                f"- **Location:** `{location}`",
                f"- **Reason:** {reasons}",
            ])
            if trigger.subscription.description:
                lines.append(f"- **Description:** {trigger.subscription.description}")

            if trigger.subscription.anchors:
                lines.extend([
                    "",
                    "**Watched lines:**",
                    "```",
                ])
                lines.extend(trigger.subscription.anchors.lines)
                lines.extend(["```", ""])
            else:
                lines.append("")

    # Proposed updates
    if result.proposals:
        lines.extend([
            "## Proposed Updates",
            "",
            "These subscriptions need their locations updated (no content changes):",
            "",
        ])

        for prop in result.proposals:
            label = f" ({prop.subscription.label})" if prop.subscription.label else ""
            old_loc = f"{prop.old_path}:{prop.old_start}-{prop.old_end}"
            new_loc = f"{prop.new_path}:{prop.new_start}-{prop.new_end}"
            reasons = ", ".join(prop.reasons)

            lines.extend([
                f"### `{prop.subscription_id[:8]}`{label}",
                "",
                f"- **Old:** `{old_loc}`",
                f"- **New:** `{new_loc}`",
                f"- **Reason:** {reasons}",
            ])
            if prop.shift:
                lines.append(f"- **Shift:** {prop.shift:+d} lines")
            lines.append("")

    # Unchanged subscriptions
    if result.unchanged:
        lines.extend([
            "## Unchanged Subscriptions",
            "",
            "These subscriptions were not affected by changes:",
            "",
        ])

        for sub in result.unchanged:
            label = f" ({sub.label})" if sub.label else ""
            location = f"{sub.path}:{sub.start_line}-{sub.end_line}"
            lines.append(f"- `{sub.id[:8]}`{label} - `{location}`")

        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
