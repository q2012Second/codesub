Below is a concrete, developer-followable implementation plan for a Python POC CLI that lets you “subscribe” to file line ranges, detect changes via git diff, and keep subscriptions valid across line shifts and file renames.

⸻

1. Project structure

Use a standard src/ layout + a hidden repo-local config directory.

code-subscription-tool/
  pyproject.toml
  README.md
  src/
    codesub/
      __init__.py
      cli.py
      errors.py
      models.py
      config_store.py
      git_repo.py
      diff_parser.py
      detector.py
      update_doc.py
      updater.py
      utils.py
  tests/
    conftest.py
    test_location_spec.py
    test_config_store.py
    test_git_repo.py
    test_diff_parser.py
    test_detector_triggers.py
    test_detector_shifts.py
    test_rename_detection.py
    test_apply_updates.py
    test_cli_integration.py

Repo-local state (created inside the target repository you run the tool in):

<your-repo>/
  .codesub/
    subscriptions.json
    last_update_docs/
      2026-01-22T120102Z_updates.json
      2026-01-22T120102Z_updates.md

Key design choice (simplifies everything for a POC):
	•	The subscriptions config has a single shared baseline commit (baseline_ref).
	•	scan compares baseline_ref -> target_ref and reports:
	•	triggered subscriptions (the watched lines changed)
	•	proposed updates (renames / line shifts), to keep subscriptions aligned to target_ref
	•	apply-updates applies proposals and then sets baseline_ref = target_ref.

⸻

2. Data models

2.1 Config file format

Use JSON (stdlib-only, no YAML dependency), with a schema version.

.codesub/subscriptions.json:

{
  "schema_version": 1,
  "repo": {
    "baseline_ref": "abc123deadbeef...",
    "created_at": "2026-01-22T12:00:00Z",
    "updated_at": "2026-01-22T12:00:00Z"
  },
  "subscriptions": [
    {
      "id": "7d7c20c2-9b03-4ae8-bcda-8a52b9ec6a8a",
      "path": "services/address/Address.java",
      "start_line": 42,
      "end_line": 45,
      "label": "Address.street contract",
      "description": "Watch street max length / validation rules.",
      "anchors": {
        "context_before": ["  // Address fields", "  private String street;"],
        "lines": ["  @Size(max=100)", "  private String street;"],
        "context_after": ["  private String city;", "  private String zip;"]
      },
      "created_at": "2026-01-22T12:00:00Z",
      "updated_at": "2026-01-22T12:00:00Z",
      "active": true
    }
  ]
}

Why store anchors?

Anchors are not required to detect changes (diff + line ranges is enough), but they are useful for:
	•	generating a human-friendly update document (“this subscription was watching these lines…”)
	•	optional future enhancement: “fuzzy relocation” when a file is heavily edited

For the POC, anchors are used mainly for display and for re-snapshotting after applying updates.

2.2 Python models

In models.py use dataclasses:

@dataclass
class Anchor:
    context_before: list[str]
    lines: list[str]
    context_after: list[str]

@dataclass
class Subscription:
    id: str
    path: str                 # repo-relative, POSIX-style
    start_line: int           # 1-based inclusive
    end_line: int             # 1-based inclusive
    label: str | None = None
    description: str | None = None
    anchors: Anchor | None = None
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


⸻

3. Core components

3.1 GitRepo (git wrapper)

File: git_repo.py

Responsibilities:
	•	locate repo root (git rev-parse --show-toplevel)
	•	resolve commits (git rev-parse <ref>)
	•	get current HEAD (git rev-parse HEAD)
	•	get file content at a ref (git show <ref>:<path>)
	•	get diffs:
	•	patch diff with hunks (git diff -U0 --find-renames <base> <target>)
	•	name-status for rename detection (git diff --name-status -M --find-renames <base> <target>)

Implementation notes:
	•	use subprocess.run([...], capture_output=True, text=True, check=False)
	•	normalize paths to repo-relative POSIX (pathlib.Path(...).as_posix())

Key functions:

class GitRepo:
    def __init__(self, start_dir: str = "."): ...
    def root(self) -> Path: ...
    def head(self) -> str: ...
    def resolve_ref(self, ref: str) -> str: ...
    def show_file(self, ref: str, path: str) -> list[str]: ...
    def diff_patch(self, base: str, target: str) -> str: ...
    def diff_name_status(self, base: str, target: str) -> str: ...

3.2 ConfigStore

File: config_store.py

Responsibilities:
	•	read/write .codesub/subscriptions.json
	•	validate schema version
	•	CRUD operations on subscriptions
	•	maintain repo.baseline_ref

Key functions:

class ConfigStore:
    def load(self) -> Config: ...
    def save(self, cfg: Config) -> None: ...
    def init(self, baseline_ref: str) -> None: ...
    def add_subscription(self, sub: Subscription) -> None: ...
    def list_subscriptions(self) -> list[Subscription]: ...
    def remove_subscription(self, sub_id: str) -> None: ...
    def update_subscription(self, sub: Subscription) -> None: ...

3.3 DiffParser

File: diff_parser.py

Responsibilities:
	•	parse unified diff text into structured objects
	•	parse hunk headers (the crucial part for line math)
	•	optionally store file-level metadata (new file, deleted file)

Models:

@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int

@dataclass
class FileDiff:
    old_path: str
    new_path: str
    hunks: list[Hunk]
    is_rename: bool
    is_new_file: bool
    is_deleted_file: bool

3.4 Detector (change detection + shift proposals)

File: detector.py

Responsibilities:
	•	determine which subscriptions are triggered
	•	compute proposed updated (path, start/end) for non-triggered subscriptions due to:
	•	file renames
	•	line shifts from edits before the subscription range
	•	generate result object consumed by CLI and update-doc generator

Outputs:

@dataclass
class Trigger:
    subscription_id: str
    path: str
    start_line: int
    end_line: int
    reasons: list[str]          # e.g., ["overlap_hunk", "file_deleted", "insert_inside_range"]
    matching_hunks: list[Hunk]

@dataclass
class Proposal:
    subscription_id: str
    old_path: str
    old_start: int
    old_end: int
    new_path: str
    new_start: int
    new_end: int
    reasons: list[str]          # ["rename", "line_shift"]
    confidence: str             # "high" for POC (math-based)
    shift: int | None = None

3.5 UpdateDoc writer

File: update_doc.py

Responsibilities:
	•	write a machine-readable JSON update document (used by apply-updates)
	•	write an optional markdown summary for humans

JSON schema suggestion:

{
  "schema_version": 1,
  "generated_at": "2026-01-22T12:01:02Z",
  "base_ref": "abc123...",
  "target_ref": "def456...",
  "triggers": [ ... ],
  "proposals": [ ... ]
}

3.6 Updater (apply updates)

File: updater.py

Responsibilities:
	•	read update doc JSON
	•	apply accepted proposals to config:
	•	update subscription path
	•	update start/end lines
	•	re-snapshot anchors from target_ref for updated subscriptions
	•	set config baseline to target_ref

⸻

4. CLI interface

Use stdlib argparse for the POC. Entry point: codesub.

Commands

codesub init

Create .codesub/subscriptions.json with baseline = HEAD by default.

Args:
	•	--baseline <ref> (default HEAD)
	•	--force overwrite if exists

codesub add <location>

Subscribe to a line range.

Location formats:
	•	path/to/file:42 (single line)
	•	path/to/file:42-45 (range)

Options:
	•	--label "text"
	•	--desc "text"
	•	--context N (default 2; number of lines before/after stored as anchors)

Behavior:
	•	uses config baseline ref
	•	reads file content at baseline (git show <baseline>:<path>)
	•	stores anchors

codesub list

List subscriptions.

Options:
	•	--json
	•	--verbose (include anchors preview)

codesub remove <subscription-id>

Remove/deactivate.

Options:
	•	--hard (delete) vs default soft (active=false)

codesub scan

Analyze changes between baseline and target and report triggered subs + propose updates.

Args:
	•	--base <ref> (default config baseline)
	•	--target <ref> (default HEAD)
	•	--write-updates <path> (write JSON update doc)
	•	--write-md <path> (optional markdown)
	•	--json (print results as JSON)
	•	--fail-on-trigger (exit code 2 if any triggers)

codesub apply-updates <update_doc.json>

Apply update proposals and move baseline to target.

Options:
	•	--dry-run
	•	--only <subscription-id> (apply subset)

⸻

5. Algorithm descriptions

5.1 Parse git diffs (unified diff)

Use:
	•	Patch/hunks:
	•	git diff -U0 --find-renames <base> <target>
	•	Rename detection:
	•	git diff --name-status -M --find-renames <base> <target>

Hunk parsing

Parse lines matching:

@@ -old_start,old_count +new_start,new_count @@

Counts may be omitted; default to 1 if missing.

Regex:

r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@"

Store hunks per file.

File block parsing

Detect new file / deleted file from diff headers:
	•	new file mode ... => is_new_file=True
	•	deleted file mode ... => is_deleted_file=True
	•	diff --git a/old b/new => old_path/new_path (strip a/ b/)

For POC, you can rely on --name-status for renames and deletions, but parsing these flags makes reporting clearer.

5.2 Match subscriptions to changes

Given:
	•	Subscription (path, start_line, end_line) in base version
	•	FileDiff hunks describing edits from base -> target

Define trigger conditions:
	1.	Overlapping modification/deletion
If a hunk replaces/deletes old lines (old_count > 0) and overlaps subscription range:

	•	old hunk range = [old_start, old_start + old_count - 1]
	•	overlap if:
	•	max(sub_start, hunk_start) <= min(sub_end, hunk_end)

Then trigger with reason "overlap_hunk".
	2.	Insertion inside the watched region
A pure insertion hunk has old_count == 0 and represents “insert after old_start”.

For the POC, treat insertions between watched lines as a trigger because it makes a simple contiguous “line range” ambiguous to keep updated.

Trigger if:
	•	sub_start <= hunk.old_start < sub_end

Reason: "insert_inside_range"
	3.	File deleted
If file status indicates deletion, trigger reason "file_deleted".

Implementation outline

def is_triggered(sub, file_diff) -> Trigger | None:
    if file_diff.is_deleted_file:
        return Trigger(..., reasons=["file_deleted"], matching_hunks=[])

    matches = []
    reasons = []
    for hunk in file_diff.hunks:
        if hunk.old_count > 0:
            h_start = hunk.old_start
            h_end = hunk.old_start + hunk.old_count - 1
            if ranges_overlap(sub.start, sub.end, h_start, h_end):
                matches.append(hunk)
                reasons.append("overlap_hunk")
        else:
            # insertion after old_start
            if sub.start <= hunk.old_start < sub.end:
                matches.append(hunk)
                reasons.append("insert_inside_range")

    if reasons:
        return Trigger(..., reasons=unique(reasons), matching_hunks=matches)
    return None

5.3 Calculate line number shifts (for maintenance proposals)

Goal: update (start_line, end_line) when changes before the subscription range shift line numbers.

Only do this for non-triggered subscriptions.

Compute shift

For a given subscription range [S, E]:

Process hunks in ascending old_start. Maintain shift = 0.

For each hunk:
	•	delta = new_count - old_count

Case A: insertion-only (old_count == 0)
	•	insertion occurs after line old_start
	•	it affects all lines with original line number > old_start
	•	therefore it shifts the subscription if old_start < S:

if hunk.old_start < S:
    shift += delta  # delta == new_count here

Case B: replacement/deletion (old_count > 0)
	•	old affected range ends at old_end = old_start + old_count - 1
	•	it shifts the subscription if the entire hunk is strictly before S:

if old_end < S:
    shift += delta
elif hunk.old_start > E:
    break  # hunks beyond subscription range won't affect it
else:
    # would overlap; but we excluded triggered subs earlier
    pass

Finally propose:
	•	new_start = S + shift
	•	new_end = E + shift

When to create a proposal

Create a proposal if either:
	•	shift != 0
	•	file is renamed (path changes)

Confidence can be "high" because it’s deterministic arithmetic based on diff hunks.

5.4 Detect file renames

Parse:

git diff --name-status -M --find-renames <base> <target>

Lines examples:
	•	R100\told/path.txt\tnew/path.txt
	•	D\tdeleted.txt
	•	M\tmodified.txt

Algorithm:
	•	if status starts with R, split into three fields; map old -> new.
	•	store deletion set for D if useful.

In scanning:
	•	subscription’s old_path is how it appears in baseline.
	•	propose new_path = rename_map.get(old_path, old_path).

Even if file contents didn’t change (no hunks), still propose rename update.

⸻

6. Implementation phases (incremental, testable)

Each phase ends with a runnable CLI and tests.

Phase 1 — Skeleton + config + init/list/add/remove

Deliverables:
	•	codesub init
	•	codesub add
	•	codesub list
	•	codesub remove
	•	JSON config read/write

Tests:
	•	config roundtrip (load/save)
	•	parsing path:line and path:start-end
	•	add stores anchors (mock GitRepo.show_file)

Phase 2 — GitRepo wrapper (real git)

Deliverables:
	•	GitRepo.root(), head(), resolve_ref()
	•	show_file(ref, path) returning correct lines

Tests:
	•	use temp git repo fixture in tests/:
	•	init repo, commit a file, verify show_file(HEAD, ...)

Phase 3 — Diff parsing

Deliverables:
	•	DiffParser.parse_patch() returns FileDiff and hunks
	•	DiffParser.parse_name_status() returns rename map + status map

Tests:
	•	feed static diff strings into parser
	•	verify hunks parsed correctly (including omitted counts)

Phase 4 — Trigger detection (scan basic)

Deliverables:
	•	codesub scan --base X --target Y
	•	report triggered subscriptions (text output + optional --json)

Tests:
	•	repo fixture:
	•	create subscription on lines 2-3
	•	commit change that modifies those lines
	•	scan detects trigger
	•	test insertion-inside-range triggers as defined

Phase 5 — Shift + rename proposals + update document generation

Deliverables:
	•	scan also outputs proposals for:
	•	line shifts from edits before range
	•	renames from name-status
	•	--write-updates updates.json
	•	optional --write-md updates.md

Tests:
	•	shift test:
	•	subscribe to lines 4-5
	•	modify file by inserting line at top
	•	scan proposes updated range 5-6
	•	rename test:
	•	rename file via git mv
	•	scan proposes path update

Phase 6 — Apply updates

Deliverables:
	•	codesub apply-updates updates.json
	•	applies new path + ranges
	•	re-snapshots anchors at target_ref
	•	updates config baseline to target_ref

Tests:
	•	after apply, config reflects new ranges
	•	baseline updated
	•	anchors match file content at target commit

Phase 7 — Polish for POC usability

Deliverables:
	•	better output formatting (group triggered vs proposed)
	•	--fail-on-trigger for CI usage
	•	soft delete vs hard delete
	•	helpful error messages:
	•	“config not initialized”
	•	“path not found in baseline ref”
	•	invalid ranges (start <= end, within file bounds)

⸻

7. Example usage (main workflow)

1) Initialize in a repo

cd my-microservice-repo
codesub init

2) Add subscriptions

Subscribe to Java model lines:

codesub add services/java/src/main/java/com/acme/Address.java:42-45 \
  --label "Address.street contract" \
  --desc "Watch max length / validation for downstream consumers."

Subscribe to a single line:

codesub add services/python/app/consumer.py:118 --label "Consumes Address.street"

List:

codesub list --verbose

3) After pulling changes, scan baseline -> new HEAD

codesub scan --target HEAD \
  --write-updates .codesub/last_update_docs/2026-01-22_updates.json \
  --write-md .codesub/last_update_docs/2026-01-22_updates.md

Typical output (text):
	•	Triggered:
	•	Address.street contract (lines overlapped a diff hunk)
	•	Proposed updates:
	•	Consumes Address.street moved from consumer.py:118 to consumer.py:121 (shift +3)
	•	Address.street contract file renamed Address.java -> AddressEntity.java (rename)

4) Apply the proposed maintenance updates

codesub apply-updates .codesub/last_update_docs/2026-01-22_updates.json

Now your subscriptions are aligned to the new baseline (the target commit you scanned).

5) Use in CI (optional)

Fail build if any watched region changed:

codesub scan --target HEAD --fail-on-trigger

Exit codes suggestion:
	•	0 = no triggers
	•	2 = triggers found
	•	1 = tool error (bad config, git failure)

⸻

Optional (nice-to-have) enhancements after the POC

Not required for your stated POC, but easy next steps:
	•	Fuzzy relocation using anchors when overlap occurs (use difflib.SequenceMatcher to find anchor block in new file).
	•	Support multiple “profiles” (team-specific subscription sets).
	•	codesub scan --against origin/main convenience.
	•	Output formats: GitHub annotations, JUnit XML, etc.

⸻

If you want, I can also include a minimal set of function signatures + pseudocode for each module (almost a scaffold you can paste in), but the plan above should already be detailed enough for a developer to implement the POC step-by-step.
