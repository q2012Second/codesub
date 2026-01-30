"""Change detection for codesub."""

from typing import TYPE_CHECKING

from .diff_parser import DiffParser, ranges_overlap
from .git_repo import GitRepo
from .models import (
    FileDiff,
    Hunk,
    MemberFingerprint,
    Proposal,
    ScanResult,
    SemanticTarget,
    Subscription,
    Trigger,
)

if TYPE_CHECKING:
    from typing import Any

    from .semantic import Construct
    from .semantic.indexer_protocol import SemanticIndexer


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

        # Cache for indexed constructs: (path, language) -> list[Construct]
        # Avoids re-parsing the same file for multiple subscriptions
        construct_cache: dict[tuple[str, str], list] = {}

        for sub in active_subs:
            # Check if semantic subscription
            if sub.semantic is not None:
                trigger, proposal = self._check_semantic(
                    sub, base_ref, target_ref, rename_map, status_map,
                    file_diffs, construct_cache
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

    def _search_cross_file(
        self,
        semantic: SemanticTarget,
        old_path: str,
        new_path: str,
        target_ref: str | None,
        file_diffs: list[FileDiff],
        status_map: dict[str, str],
        construct_cache: dict[tuple[str, str], list],
    ) -> tuple[list[tuple[str, "Construct"]], str]:
        """Search for construct in other files from the diff.

        Args:
            semantic: The semantic target to search for.
            old_path: Original subscription path to skip.
            new_path: Renamed path to skip (may be same as old_path).
            target_ref: Target ref for reading files.
            file_diffs: List of file diffs to search.
            status_map: Path to status mapping.
            construct_cache: Cache of indexed constructs per file.

        Returns:
            Tuple of (matches, best_match_tier).
            matches is list of (file_path, Construct) tuples.
            best_match_tier is "exact" | "body" | "interface" | "none".
        """
        from .errors import UnsupportedLanguageError
        from .semantic import detect_language, get_indexer

        target_language = semantic.language
        all_matches: list[tuple[str, "Construct"]] = []
        best_tier = "none"
        tier_priority = {"exact": 0, "body": 1, "interface": 2, "none": 3}
        skip_paths = {old_path, new_path}

        for fd in file_diffs:
            candidate_path = fd.new_path

            # Skip original file (both old and new paths)
            if candidate_path in skip_paths or fd.old_path in skip_paths:
                continue

            # Skip deleted files
            if fd.is_deleted_file or status_map.get(fd.old_path) == "D":
                continue

            # Check language compatibility
            try:
                candidate_language = detect_language(candidate_path)
                if candidate_language != target_language:
                    continue
            except UnsupportedLanguageError:
                continue

            # Check cache first
            cache_key = (candidate_path, target_language)
            if cache_key in construct_cache:
                constructs = construct_cache[cache_key]
            else:
                # Get file content
                try:
                    if target_ref:
                        source = "\n".join(self.repo.show_file(target_ref, candidate_path))
                    else:
                        with open(self.repo.root / candidate_path, encoding="utf-8") as f:
                            source = f.read()
                except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError):
                    continue

                # Index the file and cache
                indexer = get_indexer(target_language)
                constructs = indexer.index_file(source, candidate_path)
                construct_cache[cache_key] = constructs

            # Find matches using candidates API
            matches, tier = self._find_hash_candidates(semantic, constructs)
            for match in matches:
                all_matches.append((candidate_path, match))
                if tier_priority[tier] < tier_priority[best_tier]:
                    best_tier = tier

        return all_matches, best_tier

    def _check_semantic(
        self,
        sub: Subscription,
        base_ref: str,
        target_ref: str | None,
        rename_map: dict[str, str],
        status_map: dict[str, str],
        file_diffs: list[FileDiff],
        construct_cache: dict[tuple[str, str], list],
    ) -> tuple[Trigger | None, Proposal | None]:
        """Check semantic subscription for changes.

        Uses a 3-stage detection strategy:
        - Stage 1: Exact qualname match in same/renamed file
        - Stage 2: Hash-based search in same/renamed file
        - Stage 3: Cross-file hash search in other files from the diff
        """
        from .errors import UnsupportedLanguageError
        from .semantic import get_indexer

        assert sub.semantic is not None  # Type narrowing

        try:
            indexer = get_indexer(sub.semantic.language)
        except UnsupportedLanguageError as e:
            # Return AMBIGUOUS trigger for unsupported languages
            return (
                Trigger(
                    subscription_id=sub.id,
                    subscription=sub,
                    path=sub.path,
                    start_line=sub.start_line,
                    end_line=sub.end_line,
                    reasons=["unsupported_language"],
                    matching_hunks=[],
                    change_type="AMBIGUOUS",
                    details={"error": str(e)},
                ),
                None,
            )

        old_path = sub.path
        new_path = rename_map.get(old_path, old_path)

        # Track why we might fail, for final error message
        file_deleted = status_map.get(old_path) == "D"
        file_read_failed = False
        new_source: str | None = None

        # Try to get new file content (may fail if deleted or unreadable)
        if not file_deleted:
            try:
                if target_ref:
                    new_source = "\n".join(self.repo.show_file(target_ref, new_path))
                else:
                    with open(self.repo.root / new_path, encoding="utf-8") as f:
                        new_source = f.read()
            except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError):
                file_read_failed = True

        # Stage 1 & 2: Only if we have new_source
        if new_source is not None:
            # Stage 1: Exact match by qualname
            new_construct = indexer.find_construct(
                new_source, new_path, sub.semantic.qualname, sub.semantic.kind
            )

            if new_construct:
                # Found by exact qualname - check for changes

                # Cache the constructs list for reuse
                cache_key = (new_path, sub.semantic.language)
                if cache_key not in construct_cache:
                    construct_cache[cache_key] = indexer.index_file(new_source, new_path)
                constructs = construct_cache[cache_key]

                # For container subscriptions, delegate to container member check
                if sub.semantic.include_members:
                    trigger = self._check_container_members(
                        sub, new_source, new_path, indexer, new_construct, constructs
                    )
                else:
                    trigger = self._classify_semantic_change(sub, new_construct)

                proposal = None

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

            # Stage 2: Hash-based search in same file
            cache_key = (new_path, sub.semantic.language)
            if cache_key in construct_cache:
                new_constructs = construct_cache[cache_key]
            else:
                new_constructs = indexer.index_file(new_source, new_path)
                construct_cache[cache_key] = new_constructs

            match = self._find_by_hash(sub.semantic, new_constructs)

            if match:
                # For container subscriptions, use container member check
                if sub.semantic.include_members:
                    trigger = self._check_container_members(
                        sub, new_source, new_path, indexer, match, new_constructs
                    )
                else:
                    trigger = self._classify_semantic_change(sub, match)

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

        # Stage 3: Cross-file search (always attempted, even if file deleted)
        cross_matches, match_tier = self._search_cross_file(
            sub.semantic, old_path, new_path, target_ref, file_diffs,
            status_map, construct_cache
        )

        if len(cross_matches) == 1:
            # Found in exactly one other file
            found_path, found_construct = cross_matches[0]

            # For container subscriptions, need to index the file for member comparison
            if sub.semantic.include_members:
                # Get or cache the constructs for this file
                cache_key = (found_path, sub.semantic.language)
                if cache_key in construct_cache:
                    found_constructs = construct_cache[cache_key]
                else:
                    if target_ref:
                        found_source = "\n".join(self.repo.show_file(target_ref, found_path))
                    else:
                        with open(self.repo.root / found_path, encoding="utf-8") as f:
                            found_source = f.read()
                    found_constructs = indexer.index_file(found_source, found_path)
                    construct_cache[cache_key] = found_constructs

                trigger = self._check_container_members(
                    sub, found_source, found_path, indexer, found_construct, found_constructs
                )
            else:
                trigger = self._classify_semantic_change(sub, found_construct)

            # Set confidence based on match tier
            confidence = "high" if match_tier == "exact" else "medium" if match_tier == "body" else "low"

            proposal = Proposal(
                subscription_id=sub.id,
                subscription=sub,
                old_path=old_path,
                old_start=sub.start_line,
                old_end=sub.end_line,
                new_path=found_path,
                new_start=found_construct.start_line,
                new_end=found_construct.end_line,
                reasons=["moved_cross_file"],
                confidence=confidence,
                new_qualname=found_construct.qualname if found_construct.qualname != sub.semantic.qualname else None,
                new_kind=found_construct.kind if found_construct.kind != sub.semantic.kind else None,
            )
            return trigger, proposal

        if len(cross_matches) > 1:
            # Found in multiple files (duplicate/ambiguous)
            if sub.trigger_on_duplicate:
                locations = [f"{path}:{c.start_line}" for path, c in cross_matches]
                return (
                    Trigger(
                        subscription_id=sub.id,
                        subscription=sub,
                        path=old_path,
                        start_line=sub.start_line,
                        end_line=sub.end_line,
                        reasons=["duplicate_found"],
                        matching_hunks=[],
                        change_type="AMBIGUOUS",
                        details={"locations": locations},
                    ),
                    None,
                )
            # Default: duplicates are ambiguous, treat as unchanged (no trigger, no proposal)
            return (None, None)

        # Not found anywhere - determine the appropriate missing reason
        if file_deleted:
            reason = "file_deleted"
        elif file_read_failed:
            reason = "file_not_found"
        else:
            reason = "semantic_target_missing"

        return (
            Trigger(
                subscription_id=sub.id,
                subscription=sub,
                path=old_path,
                start_line=sub.start_line,
                end_line=sub.end_line,
                reasons=[reason],
                matching_hunks=[],
                change_type="MISSING",
            ),
            None,
        )

    def _check_container_members(
        self,
        sub: Subscription,
        new_source: str,
        new_path: str,
        indexer: "SemanticIndexer",
        current_container: "Construct",
        constructs: "list[Construct]",
    ) -> Trigger | None:
        """Check container subscription for member changes.

        Args:
            sub: The container subscription.
            new_source: Current source code.
            new_path: Current file path.
            indexer: The language indexer.
            current_container: The matched container construct (may have different qualname if renamed).
            constructs: Pre-indexed constructs from the file.

        Returns a trigger if any member changed, was added, or was removed.
        """
        assert sub.semantic is not None
        semantic = sub.semantic

        # Determine the container qualnames for comparison
        baseline_container_qualname = semantic.baseline_container_qualname or semantic.qualname
        current_container_qualname = current_container.qualname

        # Get current members using the CURRENT container qualname
        current_members = indexer.get_container_members(
            new_source, new_path, current_container_qualname, semantic.include_private,
            constructs=constructs
        )

        # Build lookup by RELATIVE member ID (strip container prefix)
        current_by_relative_id: dict[str, "Construct"] = {}
        for m in current_members:
            relative_id = m.qualname[len(current_container_qualname) + 1:]  # +1 for dot
            current_by_relative_id[relative_id] = m

        # Get baseline members (already stored by relative ID)
        baseline_members = semantic.baseline_members or {}

        member_changes: list[dict[str, Any]] = []
        members_added: list[str] = []
        members_removed: list[str] = []

        # Check for changes and removals (compare by relative ID)
        for relative_id, baseline_fp in baseline_members.items():
            if relative_id not in current_by_relative_id:
                members_removed.append(relative_id)
                member_changes.append({
                    "relative_id": relative_id,
                    "baseline_qualname": f"{baseline_container_qualname}.{relative_id}",
                    "kind": baseline_fp.kind,
                    "change_type": "MISSING",
                })
            else:
                current = current_by_relative_id[relative_id]
                if baseline_fp.interface_hash != current.interface_hash:
                    member_changes.append({
                        "relative_id": relative_id,
                        "qualname": current.qualname,
                        "kind": current.kind,
                        "change_type": "STRUCTURAL",
                        "reason": "interface_changed",
                    })
                elif baseline_fp.body_hash != current.body_hash:
                    member_changes.append({
                        "relative_id": relative_id,
                        "qualname": current.qualname,
                        "kind": current.kind,
                        "change_type": "CONTENT",
                        "reason": "body_changed",
                    })

        # Check for additions (compare by relative ID)
        for relative_id, current in current_by_relative_id.items():
            if relative_id not in baseline_members:
                members_added.append(relative_id)
                member_changes.append({
                    "relative_id": relative_id,
                    "qualname": current.qualname,
                    "kind": current.kind,
                    "change_type": "ADDED",
                })

        # Check container-level changes
        container_changes: dict[str, Any] = {}

        # Check for container rename
        if current_container_qualname != baseline_container_qualname:
            container_changes["renamed"] = True
            container_changes["old_qualname"] = baseline_container_qualname
            container_changes["new_qualname"] = current_container_qualname

        # Check for decorator/inheritance changes if tracking decorators
        if semantic.track_decorators:
            if current_container.interface_hash != semantic.interface_hash:
                container_changes["interface_changed"] = True
                member_changes.append({
                    "relative_id": None,
                    "qualname": current_container_qualname,
                    "kind": semantic.kind,
                    "change_type": "STRUCTURAL",
                    "reason": "container_interface_changed",
                })

        if not member_changes and not container_changes:
            return None  # No changes detected

        # Build trigger with aggregate details
        details: dict[str, Any] = {
            "container_qualname": current_container_qualname,
            "baseline_container_qualname": baseline_container_qualname,
            "parent_subscription_id": sub.id,
            "container_changes": container_changes,
            "member_changes": member_changes,
            "members_added": members_added,
            "members_removed": members_removed,
        }

        reasons: list[str] = []
        if container_changes.get("renamed"):
            reasons.append("container_renamed")
        if members_added:
            reasons.append("member_added")
        if members_removed:
            reasons.append("member_removed")
        if any(
            c["change_type"] == "STRUCTURAL" and c.get("reason") != "container_interface_changed"
            for c in member_changes
        ):
            reasons.append("member_interface_changed")
        if any(c["change_type"] == "CONTENT" for c in member_changes):
            reasons.append("member_body_changed")
        if container_changes.get("interface_changed"):
            reasons.append("container_interface_changed")

        return Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=new_path,
            start_line=current_container.start_line,
            end_line=current_container.end_line,
            reasons=reasons,
            matching_hunks=[],
            change_type="AGGREGATE",
            details=details,
        )

    def _classify_semantic_change(
        self,
        sub: Subscription,
        new_construct: "Construct",
    ) -> Trigger | None:
        """Classify change type between subscription fingerprints and new construct.

        Compares stored fingerprints in sub.semantic against new_construct.
        """
        if sub.semantic is None:
            return None

        # Check interface change (type/signature)
        if sub.semantic.interface_hash != new_construct.interface_hash:
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
        if sub.semantic.body_hash != new_construct.body_hash:
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

    def _find_hash_candidates(
        self,
        semantic: SemanticTarget,
        constructs: "list[Construct]",
    ) -> tuple[list["Construct"], str]:
        """Find all constructs matching by hash, with match tier.

        Unlike _find_by_hash which returns a single result or None,
        this returns ALL matching constructs, enabling detection of
        ambiguous matches (duplicates).

        Args:
            semantic: The semantic target with fingerprints.
            constructs: List of constructs to search.

        Returns:
            Tuple of (matching_constructs, match_tier).
            match_tier is "exact" | "body" | "interface" | "none".
        """
        # Try exact match (both hashes)
        exact_matches = [
            c
            for c in constructs
            if c.interface_hash == semantic.interface_hash
            and c.body_hash == semantic.body_hash
            and c.kind == semantic.kind
        ]
        if exact_matches:
            return exact_matches, "exact"

        # Try body-only match (renamed + signature changed)
        body_matches = [
            c
            for c in constructs
            if c.body_hash == semantic.body_hash and c.kind == semantic.kind
        ]
        if body_matches:
            return body_matches, "body"

        # Try interface-only match (renamed + body changed)
        interface_matches = [
            c
            for c in constructs
            if c.interface_hash == semantic.interface_hash and c.kind == semantic.kind
        ]
        if interface_matches:
            return interface_matches, "interface"

        return [], "none"
