"""Updater for applying proposals to subscriptions."""

from typing import Any

from .config_store import ConfigStore
from .errors import SubscriptionNotFoundError
from .git_repo import GitRepo
from .models import Anchor, _utc_now
from .utils import extract_anchors


class Updater:
    """Applies update proposals to subscriptions."""

    def __init__(self, store: ConfigStore, repo: GitRepo):
        self.store = store
        self.repo = repo

    def apply(
        self,
        update_data: dict[str, Any],
        dry_run: bool = False,
    ) -> tuple[list[str], list[str]]:
        """
        Apply update proposals from an update document.

        Args:
            update_data: Parsed JSON update document.
            dry_run: If True, don't actually modify anything.

        Returns:
            Tuple of (applied_ids, warnings):
            - applied_ids: List of subscription IDs that were updated.
            - warnings: List of warning messages.
        """
        proposals = update_data.get("proposals", [])
        target_ref = update_data.get("target_ref", "")

        if not proposals:
            return [], []

        if not target_ref:
            return [], ["No target_ref in update document"]

        applied: list[str] = []
        warnings: list[str] = []

        config = self.store.load()

        # Build subscription lookup
        sub_by_id = {s.id: s for s in config.subscriptions}

        for prop in proposals:
            sub_id = prop.get("subscription_id", "")
            new_path = prop.get("new_path", "")
            new_start = prop.get("new_start", 0)
            new_end = prop.get("new_end", 0)

            # Find subscription
            sub = sub_by_id.get(sub_id)
            if not sub:
                warnings.append(f"Subscription {sub_id[:8]} not found, skipping")
                continue

            # Validate new location
            try:
                new_lines = self.repo.show_file(target_ref, new_path)
            except Exception as e:
                warnings.append(
                    f"Cannot read {new_path} at {target_ref[:12]} for {sub_id[:8]}: {e}"
                )
                continue

            if new_start < 1:
                warnings.append(
                    f"New range {new_start}-{new_end} starts before line 1 "
                    f"for {sub_id[:8]}"
                )
                continue

            if new_end > len(new_lines):
                warnings.append(
                    f"New range {new_start}-{new_end} exceeds file length "
                    f"({len(new_lines)} lines) for {sub_id[:8]}"
                )
                continue

            # Optional: verify anchor content matches (warning only)
            if sub.anchors and sub.anchors.lines:
                old_content = "\n".join(sub.anchors.lines).strip()
                new_content = "\n".join(
                    new_lines[new_start - 1 : new_end]
                ).strip()

                # Simple content check - warn if significantly different
                if old_content != new_content:
                    # Check if at least some overlap exists
                    old_words = set(old_content.split())
                    new_words = set(new_content.split())
                    if old_words and new_words:
                        overlap = len(old_words & new_words) / len(old_words)
                        if overlap < 0.5:
                            warnings.append(
                                f"Content at new location for {sub_id[:8]} differs "
                                f"significantly from original (overlap: {overlap:.0%})"
                            )

            if not dry_run:
                # Update subscription
                sub.path = new_path
                sub.start_line = new_start
                sub.end_line = new_end
                sub.updated_at = _utc_now()

                # Re-snapshot anchors
                context_before, watched_lines, context_after = extract_anchors(
                    new_lines, new_start, new_end, context=2
                )
                sub.anchors = Anchor(
                    context_before=context_before,
                    lines=watched_lines,
                    context_after=context_after,
                )

            applied.append(sub_id)

        # Save changes and update baseline
        if not dry_run and applied:
            self.store.save(config)
            self.store.update_baseline(target_ref)

        return applied, warnings
