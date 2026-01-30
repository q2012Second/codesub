According to a document (date not provided in the excerpt), the plan is to add an --include-members option for semantic subscriptions on container constructs (class/interface/enum), store a baseline snapshot of member fingerprints at subscription creation, and then emit an AGGREGATE trigger whenever the container itself or any direct member changes.  ￼ ￼

What’s solid in the plan
	•	Storing a baseline snapshot is the right call for “new member added” detection. Without remembering what existed at subscription time, you can’t reliably tell “new” vs “previously existing.” The plan explicitly recognizes this tradeoff.  ￼
	•	Trigger payload shape matches the intended direction: one trigger with change_type="AGGREGATE" and structured details including container_changes, member_changes, members_added, members_removed. That aligns with the spec’s example format.  ￼ ￼
	•	Decorators as “structural” and track_decorators defaulting to enabled is consistent with the “decorator changes should trigger by default” requirement.  ￼ ￼
	•	Update-doc serialization already supports details: the existing _trigger_to_dict includes change_type and details when present, so you can ship these richer triggers without changing the writer’s core shape.  ￼

Must-fix gaps (these will break stated requirements)

1) “Container not found ⇒ MISSING; skip Stage 2/3 relocation” breaks move/rename support

The plan explicitly says: if the container isn’t found, return a MISSING trigger immediately and skip Stage 2/3 hash relocation.  ￼ ￼

That conflicts with the requirement that:
	•	moving an entire class to a different file should be handled by the existing cross-file detection, and
	•	container-level rename is a tracked change (e.g., User → UserAccount).  ￼

If you skip Stage 2/3, the system can’t “follow” a moved/renamed container even when hashes would allow a confident match.

Recommendation: don’t short-circuit to MISSING for include_members subscriptions. Let the same Stage 2/3 matching logic run for containers, and then:
	•	produce a proposal when a match is found (path/line/qualname updated), and
	•	compute container/member diffs against the matched construct.

This also matches another stated constraint: “line range tracking needed for proposals when container moves.”  ￼

⸻

2) Python indexer currently doesn’t emit container constructs (so Python “include-members” can’t work as written)

The spec says Python supports container kinds like class/enum.  ￼

But the current PythonIndexer.index_file() builds module-level variables and then calls _extract_classes() to extract fields and methods, not the class construct itself. In _extract_classes(), the code iterates class body members and only appends constructs for assignments (fields) and methods—there is no Construct(kind="class", qualname="User", ...) emitted for the class definition.  ￼ ￼

So a semantic subscription targeting ::User (a class) would not be findable in Python, and include-members on that container won’t get off the ground.

Recommendation: extend the Python indexer to emit:
	•	a container Construct for each class definition (kind="class" and, if you want real enums, detect Enum base and use kind="enum"), and
	•	nested class constructs if “nested classes are tracked as members” is a goal.  ￼

⸻

3) Member identity is currently tied to full qualnames, which will explode on container rename

In _check_container_members, the plan builds current_by_qualname = {m.qualname: m ...} and compares against baseline_members keyed by qualname.  ￼

That works fine as long as the container qualname never changes.

But if the container renames from User to UserAccount, every member qualname changes (User.validate → UserAccount.validate), and the naive comparison will report:
	•	all old members “removed” and
	•	all new members “added”
even if nothing changed except the prefix. This also undermines the “fingerprint stability” concern.  ￼

Two good ways to fix it:
	1.	compare members by relative member id (strip the container prefix on both baseline and current, so you compare validate to validate), or
	2.	if you detect a rename via Stage 2/3, normalize baseline/current maps by stripping the baseline container prefix vs the current container prefix during comparison.

Either way, you need the concept of “baseline container qualname” vs “current container qualname,” which the current code path doesn’t have because it uses only semantic.qualname everywhere.  ￼

Other important issues / improvements

Performance: the “cached per file” assumption doesn’t hold for Stage 1 + member extraction

The plan claims member comparison is fine because “constructs are already cached per file during scan.”  ￼

But find_construct() in both Java and Python indexers re-indexes the file by calling self.index_file(source, path) every time it’s invoked.  ￼ ￼

And your plan’s flow does:
	•	Stage 1: find_construct(...) (indexes file)
	•	then get_container_members(...) (likely indexes file again unless it reuses the earlier list)

Recommendation: pass around the already-indexed construct list, or add an indexer helper that can filter members from a provided constructs list. That would make the “cached per file” statement actually true for Stage 1 paths.

CLI snippet has a likely missing import

The CLI plan code uses MemberFingerprint(...) when building baseline_members, but the shown imports only pull CONTAINER_KINDS from models. That would be a NameError unless MemberFingerprint is imported too.  ￼

(Your API snippet does import MemberFingerprint, so this looks like a CLI-only omission.)  ￼

Container-level change reporting is under-specified vs the spec

The requirements mention container-level changes like:
	•	renamed
	•	decorators changed
	•	inheritance changed  ￼

The planned implementation sets container_changes["decorators_changed"] based on interface_hash mismatch, but does not explicitly mark rename/inheritance changes.  ￼

If you implement Stage 2/3 relocation for containers, you can set:
	•	renamed = (matched.qualname != semantic.qualname)
	•	decorators_changed and inheritance_changed (if you can separate them; otherwise a single “interface changed” flag)

Test plan: adjust to match the actual requirements

The proposed tests include test_container_not_found_returns_missing and explicitly say “no Stage 2/3,” which bakes in the move/rename limitation.  ￼

But the spec expects cross-file movement handling and rename tracking.  ￼

Add/replace tests to cover:
	•	container moved to a new file (proposal + still able to compare members)
	•	container renamed (proposal + no false “all members added/removed” noise)
	•	nested class counted as a direct member (but nested class members not tracked unless separately subscribed)  ￼ ￼

Bottom line

If you keep the current “skip Stage 2/3” behavior and don’t add Python class constructs, the feature will work only in a narrow subset (mostly Java, and only when the container stays in-place and keeps the same qualname).  ￼ ￼

If you want to match the stated requirements (rename + cross-file move + nested classes), the biggest design shifts are:
	1.	don’t short-circuit container subscriptions before Stage 2/3 relocation, and
	2.	compare members by relative identity (or otherwise normalize across container renames), and
	3.	teach the Python indexer to emit container constructs.

If you want, I can rewrite the detector flow as a short “corrected pseudocode” that preserves your existing semantic relocation logic while adding member aggregation cleanly—without doubling index work.
