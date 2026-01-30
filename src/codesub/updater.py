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

                # Update semantic target if qualname changed (construct was renamed)
                new_qualname = prop.get("new_qualname")
                new_kind = prop.get("new_kind")
                if sub.semantic and (new_qualname or new_kind):
                    if new_qualname:
                        sub.semantic.qualname = new_qualname
                    if new_kind:
                        sub.semantic.kind = new_kind

                # Re-snapshot anchors
                context_before, watched_lines, context_after = extract_anchors(
                    new_lines, new_start, new_end, context=2
                )
                sub.anchors = Anchor(
                    context_before=context_before,
                    lines=watched_lines,
                    context_after=context_after,
                )

                # Recapture baseline members for container subscriptions
                if sub.semantic and sub.semantic.include_members:
                    try:
                        self._recapture_container_baseline(
                            sub, new_lines, new_path, warnings
                        )
                    except Exception:
                        # If recapture fails, log warning but don't fail the update
                        warnings.append(
                            f"Failed to recapture baseline members for {sub_id[:8]}"
                        )

            applied.append(sub_id)

        # Save changes and update baseline
        if not dry_run and applied:
            self.store.save(config)
            self.store.update_baseline(target_ref)

        return applied, warnings

    def _recapture_container_baseline(
        self,
        sub: Any,  # Subscription
        new_lines: list[str],
        new_path: str,
        warnings: list[str],
    ) -> None:
        """Recapture baseline members for container subscriptions.

        Updates the subscription's semantic target with:
        - Current container fingerprints
        - Current container qualname
        - Current member fingerprints (using relative IDs)
        """
        from .models import MemberFingerprint
        from .semantic import get_indexer

        assert sub.semantic is not None
        semantic = sub.semantic

        indexer = get_indexer(semantic.language)
        source = "\n".join(new_lines)

        # Determine the current qualname (may have changed via proposal)
        current_qualname = semantic.qualname

        # Find the container construct and index file
        all_constructs = indexer.index_file(source, new_path)
        container = indexer.find_construct(
            source, new_path, current_qualname, semantic.kind
        )

        if container:
            # Update container fingerprints
            semantic.interface_hash = container.interface_hash
            semantic.body_hash = container.body_hash
            # Update baseline container qualname to current
            semantic.baseline_container_qualname = current_qualname

        # Recapture member fingerprints with RELATIVE IDs
        members = indexer.get_container_members(
            source, new_path, current_qualname, semantic.include_private,
            constructs=all_constructs
        )
        semantic.baseline_members = {}
        for m in members:
            relative_id = m.qualname[len(current_qualname) + 1:]
            semantic.baseline_members[relative_id] = MemberFingerprint(
                kind=m.kind,
                interface_hash=m.interface_hash,
                body_hash=m.body_hash,
            )
