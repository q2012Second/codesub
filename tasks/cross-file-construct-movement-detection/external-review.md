According to a document from January 28, 2026, the overall direction of your Stage 3 plan fits the current detector architecture, but there are a couple of critical gaps that would prevent cross-file moves from being detected in some very real scenarios, plus a few “make it safer + cleaner” improvements.

High-level read: Is the plan correct and aligned?

Yes, conceptually:
	•	Detector.scan() already computes file_diffs (from the unified diff patch) and rename_map/status_map (from --name-status). Today it calls _check_semantic() without file_diffs, so Stage 3 needs an integration step (your Step 2) to get access to the diff-scoped candidate file list.  ￼
	•	_check_semantic() currently does Stage 1 (qualname in same/renamed file) then Stage 2 (hash search in same file) then returns MISSING if both fail. You’re adding Stage 3 exactly in the right place.  ￼ ￼

So the architecture fit is good.

⸻

Issues & gaps (with severity + fixes)

1) CRITICAL — Stage 3 is unreachable when the original file is deleted (or the new file can’t be read)

Problem: _check_semantic() returns MISSING immediately if status_map[old_path] == "D" (deleted file). That means “construct moved to a different file and the old file was removed” will never reach your Stage 3 cross-file search.  ￼

Similarly, if reading the “same/renamed file” at the target fails (e.g., file missing at the ref / working tree), _check_semantic() returns MISSING immediately (file_not_found), again bypassing Stage 3.  ￼

Why this matters: A pretty common refactor pattern is “move construct to a new module, delete old module”. Your plan says “skip deleted files” and “construct moved to new file (status=A)”, but the subscription’s original file being deleted is the bigger blocker.

Suggested fix:
	•	Do not early-return on file_deleted / file_not_found before Stage 3.
	•	Instead:
	1.	Compute old_path and new_path as today.
	2.	Try Stage 1/2 only if you successfully load new_source.
	3.	Always attempt Stage 3 if Stage 1/2 didn’t yield a match, even if the original file is deleted or unreadable.
	4.	If Stage 3 fails too, then decide which missing reason to return:
	•	if file_status == "D" → file_deleted
	•	else if new file read failed → file_not_found
	•	else → semantic_target_missing (current behavior)  ￼

This preserves backward behavior while enabling cross-file detection.

⸻

2) MAJOR — Duplicate handling needs a clearer contract, and _find_by_hash() hides ambiguity

Problem A (behavior spec): Your plan says “Handle duplicates (default: no trigger)” but doesn’t define what the scan returns when duplicates exist:
	•	Do you return MISSING anyway?
	•	Do you return nothing (unchanged) to avoid noise?
	•	Do you return AMBIGUOUS?

You need a concrete choice because Detector.scan() treats (None, None) as “unchanged”.  ￼

Problem B (implementation): _find_by_hash() returns None when there are multiple matches (“Ambiguous”). That means it’s impossible to distinguish “no matches” from “multiple matches” without re-implementing its logic or extending it.  ￼ ￼

Also, your Stage 3 approach (“use _find_by_hash() per file, aggregate results”) won’t catch “duplicates within a single file” because _find_by_hash() will already return None for that file.

Suggested fix:
	•	Keep _find_by_hash() for backward compatibility, but introduce a new helper like:
	•	_find_hash_candidates(target, constructs) -> tuple[list[Construct], match_tier]
	•	where match_tier could be "exact" | "body" | "interface".
	•	Stage 2 can continue using _find_by_hash() if you want no behavior change.
	•	Stage 3 can use the “candidates” API to:
	•	detect duplicates precisely,
	•	set Proposal.confidence based on tier (see minor item below),
	•	and apply your trigger_on_duplicate policy cleanly.

What to do when duplicates are found (recommended):
	•	If trigger_on_duplicate == False → return (None, None) (no trigger, no proposal), matching your “default: no trigger” requirement.
	•	If trigger_on_duplicate == True → return a Trigger(change_type="AMBIGUOUS", reasons=[...]) and no proposal. The Trigger model already supports an "AMBIGUOUS" change_type.

(If you want the user to resolve ambiguity, you could also generate multiple low-confidence proposals, but only do that if your apply/update UX can handle “multiple proposals for one subscription” safely.)

⸻

3) MAJOR — You probably don’t need _classify_cross_file_change(); fix _classify_semantic_change() instead

Your Step 4 says Stage 3 needs a new classifier because old_construct is None, but in the current implementation:
	•	_classify_semantic_change() does not actually use old_construct—it only checks that it’s not None, then compares stored hashes (sub.semantic) vs new_construct.  ￼
	•	In most normal cases, old_construct won’t be None anyway because it’s found at base_ref by qualname (the subscription was originally created there). Stage 1 failing does not imply old_construct is missing.  ￼

Suggested fix:
	•	Remove the old_construct is None guard in _classify_semantic_change() and make it depend only on sub.semantic + new_construct. That makes Stage 3 classification work without adding a second classifier and reduces duplication.  ￼

If you want to be conservative, keep a separate guard for “sub.semantic is None”.

⸻

4) MAJOR — Performance: Stage 3 could become O(subscriptions × changed_files × parse_cost)

Stage 3 as described indexes each candidate file for each “missing” subscription. On a diff touching many files and many semantic subs, that can get expensive fast.

Suggested fix (fits current architecture):
	•	Add a per-scan cache inside Detector.scan() or Detector:
	•	key: (target_ref_or_WORKING, path, language)
	•	value: list[Construct]
	•	Stage 3 can reuse the cached constructs for each candidate file instead of re-parsing.

This is especially worthwhile because get_indexer(language) is cached, but parsing/indexing the file is not.  ￼

⸻

Edge cases you should explicitly include (some are currently missing)

You listed many good ones; here are the big additions/clarifications:
	1.	Old file deleted + construct moved elsewhere
This is the critical one blocked by the early return today.  ￼
	2.	Working tree scan (target_ref=None)
_check_semantic() has special logic for reading from disk when target_ref is not provided. Stage 3 must use the same approach for candidate files.  ￼
	3.	Binary or non-text files in diff
FileDiff supports is_binary and the patch parser can detect file mode changes; your search helper should skip binary diffs.  ￼ ￼
	4.	False positives when an identical construct already exists in another changed file
Diff-scoping reduces risk, but it’s still possible (e.g., you delete a function and separately edit a file that already had the same implementation). Consider using confidence tiers and/or stricter matching in Stage 3.
	5.	Match-tier confidence
Because _find_by_hash() can fall back to body-only or interface-only, Stage 3 should ideally set Proposal.confidence to reflect how strong the match is (exact = high, body-only = medium, interface-only = low). The model supports this.

⸻

Integration notes

Passing file_diffs into _check_semantic()

Your Step 2 is correct; scan already has file_diffs and currently only uses it for line-based logic.  ￼ ￼

I’d suggest passing just a list of candidate paths (e.g., changed_paths_new = [fd.new_path for fd in file_diffs]) rather than full FileDiff objects, unless you need the flags (is_deleted_file, is_binary, etc.). If you do need them, passing the FileDiff list is fine.

Language boundaries

Use detect_language(path) (extension-based) and compare to sub.semantic.language, but be sure to catch UnsupportedLanguageError and skip. The registry is designed for that.  ￼ ￼

Where to put moved_cross_file

In this codebase, “rename” is a proposal reason, not a trigger reason; Proposal explicitly documents reasons like ["rename", "line_shift", "semantic_location"]. So moved_cross_file should probably live in Proposal.reasons too.

If you also want it visible when a CONTENT/INTERFACE trigger fires, you can append moved_cross_file to the trigger reasons in Stage 3 when you return a trigger—but that would be a behavior expansion beyond existing patterns.

⸻

Testing strategy review

Your test list is strong and maps well to the existing testing style (temp git repo, write files, commit, scan).  ￼ ￼

What I’d add/adjust:
	•	Add the “old file deleted + moved” test (critical). This will fail with current code because of the early return on file_deleted.  ￼
	•	Add explicit duplicate-behavior tests that verify your chosen contract:
	•	duplicates + trigger_on_duplicate=False → no trigger (and probably unchanged)
	•	duplicates + trigger_on_duplicate=True → AMBIGUOUS trigger (no proposal)
	•	Add a confidence-tier test if you implement match-tier confidence.
	•	Serialization tests for the new Subscription.trigger_on_duplicate field:
	•	to_dict() includes it
	•	from_dict() defaults to False when missing (backward compatibility)  ￼

⸻

Is the plan ready to implement?

Almost, but I’d treat the two items below as “must fix before implementation”:
	1.	Move/adjust early returns so Stage 3 still runs when the original file is deleted or new file can’t be read. (Critical)  ￼ ￼
	2.	Define + implement a concrete duplicates contract, ideally by extending hash search to return candidates so you can distinguish “no match” vs “ambiguous” and honor trigger_on_duplicate. (Major)  ￼

If you incorporate those, the rest of the plan is in good shape.

￼
