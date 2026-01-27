"""Change detection for codesub."""

from typing import TYPE_CHECKING

from .diff_parser import DiffParser, ranges_overlap
from .git_repo import GitRepo
from .models import FileDiff, Hunk, Proposal, ScanResult, SemanticTarget, Subscription, Trigger

if TYPE_CHECKING:
    from .semantic import Construct


class Detector:
    """Detects changes affecting subscriptions."""

    def __init__(self, repo: GitRepo):
        self.repo = repo
        self.parser = DiffParser()

    def scan(
        self,
        subscriptions: list[Subscription],
        base_ref: str,
        target_ref: str | None = None,
    ) -> ScanResult:
        """
        Scan for changes between two refs, or between a ref and working directory.

        Args:
            subscriptions: List of subscriptions to check.
            base_ref: Base git ref.
            target_ref: Target git ref, or None/empty for working directory.

        Returns:
            ScanResult with triggers, proposals, and unchanged subscriptions.
        """
        # Only process active subscriptions
        active_subs = [s for s in subscriptions if s.active]

        # Use "WORKING" to represent working directory
        display_target = target_ref or "WORKING"

        if not active_subs:
            return ScanResult(
                base_ref=base_ref,
                target_ref=display_target,
                triggers=[],
                proposals=[],
                unchanged=[],
            )

        # Get diffs
        patch_text = self.repo.diff_patch(base_ref, target_ref)
        name_status_text = self.repo.diff_name_status(base_ref, target_ref)

        # Parse diffs
        file_diffs = self.parser.parse_patch(patch_text)
        rename_map, status_map = self.parser.parse_name_status(name_status_text)

        # Build lookup by old path
        diff_by_path: dict[str, FileDiff] = {}
        for fd in file_diffs:
            diff_by_path[fd.old_path] = fd

        triggers: list[Trigger] = []
        proposals: list[Proposal] = []
        unchanged: list[Subscription] = []

        for sub in active_subs:
            # Check if semantic subscription
            if sub.semantic is not None:
                trigger, proposal = self._check_semantic(
                    sub, base_ref, target_ref, rename_map, status_map
                )
                if trigger:
                    triggers.append(trigger)
                if proposal:
                    proposals.append(proposal)
                if not trigger and not proposal:
                    unchanged.append(sub)
                continue

            # Line-based subscription
            # Check if file was renamed
            new_path = rename_map.get(sub.path, sub.path)
            is_renamed = new_path != sub.path

            # Check if file was deleted
            file_status = status_map.get(sub.path, "")
            is_deleted = file_status == "D"

            # Get diff for this file
            file_diff = diff_by_path.get(sub.path)

            # Check for triggers
            trigger = self._check_trigger(sub, file_diff, is_deleted)

            if trigger:
                triggers.append(trigger)
            else:
                # Check for proposals (shift or rename)
                proposal = self._compute_proposal(
                    sub, file_diff, is_renamed, new_path
                )
                if proposal:
                    proposals.append(proposal)
                else:
                    unchanged.append(sub)

        return ScanResult(
            base_ref=base_ref,
            target_ref=display_target,
            triggers=triggers,
            proposals=proposals,
            unchanged=unchanged,
        )

    def _check_trigger(
        self,
        sub: Subscription,
        file_diff: FileDiff | None,
        is_deleted: bool,
    ) -> Trigger | None:
        """
        Check if a subscription is triggered by changes.

        Returns:
            Trigger if triggered, None otherwise.
        """
        if is_deleted:
            return Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["file_deleted"],
                matching_hunks=[],
            )

        if file_diff is None:
            return None

        if file_diff.is_deleted_file:
            return Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["file_deleted"],
                matching_hunks=[],
            )

        matching_hunks: list[Hunk] = []
        reasons: list[str] = []

        for hunk in file_diff.hunks:
            if hunk.old_count > 0:
                # Modification or deletion: check for overlap
                hunk_start = hunk.old_start
                hunk_end = hunk.old_start + hunk.old_count - 1

                if ranges_overlap(sub.start_line, sub.end_line, hunk_start, hunk_end):
                    matching_hunks.append(hunk)
                    if "overlap_hunk" not in reasons:
                        reasons.append("overlap_hunk")
            else:
                # Pure insertion (old_count == 0)
                # In git diff, old_start is the line AFTER which new content is inserted.
                #
                # Trigger semantics (conservative - trigger if insertion could affect
                # the logical unit being watched):
                # - Insert after line 5 when watching 5-10: triggers (between watched lines)
                # - Insert after line 4 when watching 5-10: doesn't trigger (before range, will shift)
                # - Insert after line 9 when watching 5-10: triggers (between watched lines)
                # - Insert after line 10 when watching 5-10: doesn't trigger (after range)
                #
                # Condition: sub_start <= old_start < sub_end
                # This triggers when insertion is between the first and last watched lines
                # but NOT when insertion is immediately after the last line.
                if sub.start_line <= hunk.old_start < sub.end_line:
                    matching_hunks.append(hunk)
                    if "insert_inside_range" not in reasons:
                        reasons.append("insert_inside_range")

        if reasons:
            return Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=reasons,
                matching_hunks=matching_hunks,
            )

        return None

    def _compute_proposal(
        self,
        sub: Subscription,
        file_diff: FileDiff | None,
        is_renamed: bool,
        new_path: str,
    ) -> Proposal | None:
        """
        Compute a proposal for updating a subscription (shift or rename).

        Only called for non-triggered subscriptions.

        Returns:
            Proposal if updates needed, None otherwise.
        """
        shift = 0

        if file_diff is not None and file_diff.hunks:
            shift = self._calculate_shift(sub, file_diff.hunks)

        # Create proposal if there's a shift or rename
        if shift != 0 or is_renamed:
            reasons = []
            if is_renamed:
                reasons.append("rename")
            if shift != 0:
                reasons.append("line_shift")

            return Proposal(
                subscription_id=sub.id,
                subscription=sub,
                old_path=sub.path,
                old_start=sub.start_line,
                old_end=sub.end_line,
                new_path=new_path,
                new_start=sub.start_line + shift,
                new_end=sub.end_line + shift,
                reasons=reasons,
                confidence="high",
                shift=shift if shift != 0 else None,
            )

        return None

    def _calculate_shift(self, sub: Subscription, hunks: list[Hunk]) -> int:
        """
        Calculate line number shift for a subscription.

        IMPORTANT: This should only be called for non-triggered subscriptions,
        meaning no hunk overlaps with the subscription range.

        Args:
            sub: The subscription.
            hunks: List of hunks from the file diff (will be sorted if needed).

        Returns:
            Net shift in line numbers.
        """
        # Defensive sort - ensure hunks are in ascending old_start order
        sorted_hunks = sorted(hunks, key=lambda h: h.old_start)

        shift = 0
        sub_start = sub.start_line

        for hunk in sorted_hunks:
            delta = hunk.new_count - hunk.old_count

            if hunk.old_count == 0:
                # Pure insertion: affects lines > old_start
                # old_start is the line AFTER which insertion happens
                if hunk.old_start < sub_start:
                    shift += delta
            else:
                # Modification/deletion: old_end = old_start + old_count - 1
                old_end = hunk.old_start + hunk.old_count - 1

                if old_end < sub_start:
                    # Hunk is entirely before subscription
                    shift += delta
                elif hunk.old_start > sub.end_line:
                    # Hunk is entirely after subscription, stop processing
                    # (hunks are sorted)
                    break
                # else: hunk overlaps subscription, but we shouldn't reach here
                # because overlapping hunks would have triggered the subscription

        return shift

    def _check_semantic(
        self,
        sub: Subscription,
        base_ref: str,
        target_ref: str | None,
        rename_map: dict[str, str],
        status_map: dict[str, str],
    ) -> tuple[Trigger | None, Proposal | None]:
        """Check semantic subscription for changes."""
        from .semantic import PythonIndexer

        indexer = PythonIndexer()

        # Resolve file rename
        old_path = sub.path
        new_path = rename_map.get(old_path, old_path)

        # Check if file deleted
        if status_map.get(old_path) == "D":
            return (
                Trigger(
                    subscription_id=sub.id,
                    subscription=sub,
                    path=old_path,
                    start_line=sub.start_line,
                    end_line=sub.end_line,
                    reasons=["file_deleted"],
                    matching_hunks=[],
                    change_type="MISSING",
                ),
                None,
            )

        # Get old file content
        old_source = "\n".join(self.repo.show_file(base_ref, old_path))

        # Get new file content
        try:
            if target_ref:
                new_source = "\n".join(self.repo.show_file(target_ref, new_path))
            else:
                # Working directory
                with open(self.repo.root / new_path) as f:
                    new_source = f.read()
        except Exception:
            return (
                Trigger(
                    subscription_id=sub.id,
                    subscription=sub,
                    path=old_path,
                    start_line=sub.start_line,
                    end_line=sub.end_line,
                    reasons=["file_not_found"],
                    matching_hunks=[],
                    change_type="MISSING",
                ),
                None,
            )

        assert sub.semantic is not None  # Type narrowing

        # Stage 1: Exact match by qualname
        old_construct = indexer.find_construct(
            old_source, old_path, sub.semantic.qualname, sub.semantic.kind
        )
        new_construct = indexer.find_construct(
            new_source, new_path, sub.semantic.qualname, sub.semantic.kind
        )

        if new_construct:
            # Found by exact qualname - check for changes
            trigger = self._classify_semantic_change(sub, old_construct, new_construct)
            proposal = None

            # Check if path changed (file renamed)
            if old_path != new_path:
                proposal = Proposal(
                    subscription_id=sub.id,
                    subscription=sub,
                    old_path=old_path,
                    old_start=sub.start_line,
                    old_end=sub.end_line,
                    new_path=new_path,
                    new_start=new_construct.start_line,
                    new_end=new_construct.end_line,
                    reasons=["rename"],
                    confidence="high",
                )
            elif (
                new_construct.start_line != sub.start_line
                or new_construct.end_line != sub.end_line
            ):
                proposal = Proposal(
                    subscription_id=sub.id,
                    subscription=sub,
                    old_path=old_path,
                    old_start=sub.start_line,
                    old_end=sub.end_line,
                    new_path=new_path,
                    new_start=new_construct.start_line,
                    new_end=new_construct.end_line,
                    reasons=["line_shift"],
                    confidence="high",
                )

            return trigger, proposal

        # Stage 2: Hash-based search
        new_constructs = indexer.index_file(new_source, new_path)
        match = self._find_by_hash(sub.semantic, new_constructs)

        if match:
            # Found by hash - it was renamed/moved
            trigger = self._classify_semantic_change(sub, old_construct, match)
            proposal = Proposal(
                subscription_id=sub.id,
                subscription=sub,
                old_path=old_path,
                old_start=sub.start_line,
                old_end=sub.end_line,
                new_path=new_path,
                new_start=match.start_line,
                new_end=match.end_line,
                reasons=["semantic_location"],
                confidence="high",
                new_qualname=match.qualname,
                new_kind=match.kind,
            )
            return trigger, proposal

        # Not found at all
        return (
            Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=old_path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["semantic_target_missing"],
                matching_hunks=[],
                change_type="MISSING",
            ),
            None,
        )

    def _classify_semantic_change(
        self,
        sub: Subscription,
        old_construct: "Construct | None",
        new_construct: "Construct",
    ) -> Trigger | None:
        """Classify change type between old and new construct."""
        if old_construct is None or sub.semantic is None:
            return None

        old_fp = sub.semantic

        # Check interface change (type/signature)
        if old_fp.interface_hash != new_construct.interface_hash:
            return Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["interface_changed"],
                matching_hunks=[],
                change_type="STRUCTURAL",
            )

        # Check body change (value/implementation)
        if old_fp.body_hash != new_construct.body_hash:
            return Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=sub.path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=["body_changed"],
                matching_hunks=[],
                change_type="CONTENT",
            )

        # No meaningful change (cosmetic only)
        return None

    def _find_by_hash(
        self,
        semantic: SemanticTarget,
        constructs: "list[Construct]",
    ) -> "Construct | None":
        """Find construct by hash matching."""
        # Try exact match (both hashes)
        matches = [
            c
            for c in constructs
            if c.interface_hash == semantic.interface_hash
            and c.body_hash == semantic.body_hash
            and c.kind == semantic.kind
        ]
        if len(matches) == 1:
            return matches[0]

        # Try body-only match (renamed + signature changed)
        matches = [
            c
            for c in constructs
            if c.body_hash == semantic.body_hash and c.kind == semantic.kind
        ]
        if len(matches) == 1:
            return matches[0]

        # Try interface-only match (renamed + body changed)
        matches = [
            c
            for c in constructs
            if c.interface_hash == semantic.interface_hash and c.kind == semantic.kind
        ]
        if len(matches) == 1:
            return matches[0]

        return None
