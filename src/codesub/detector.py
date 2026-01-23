"""Change detection for codesub."""

from .diff_parser import DiffParser, ranges_overlap
from .git_repo import GitRepo
from .models import FileDiff, Hunk, Proposal, ScanResult, Subscription, Trigger


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
