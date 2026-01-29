Revised Implementation Plan: Semantic Code Subscriptions

(Repo context used: chat-context.txt  ￼)

MVP Scope

Included in v1 (MVP)
	•	Python-only semantic subscriptions for:
	•	class definitions
	•	top-level function definitions
	•	method definitions (functions inside classes)
	•	Unified subscription model: keep the existing Subscription model and add an optional semantic payload (do not create a separate SemanticSubscription table/model).
	•	Two-stage matching only (per feedback):
	1.	Stage 1 (Exact FQN): same path + qualname
	2.	Stage 2 (Rename/move w/ exact fingerprint match): same interface_hash + body_hash, different path/qualname
	•	Change classification implemented for semantic subs:
	•	STRUCTURAL → trigger (signature/decorators/bases changed)
	•	CONTENT → trigger (body tokens changed)
	•	LOCATION → proposal (moved/renamed but fingerprints unchanged)
	•	COSMETIC → no trigger (formatting/comments only)
	•	Backward compatibility preserved:
	•	existing line-based subscriptions continue to work unchanged
	•	existing scan logic remains for non-semantic subs (git diff overlap + shift/rename proposals) ￼ ￼
	•	UX additions:
	•	Add a codesub symbols command to help users discover valid semantic targets before subscribing (addresses “unclear UX”).
	•	API support:
	•	Existing POST /api/subscriptions continues working, but location will accept semantic FQNs (path::qualname) in addition to line ranges (path:start-end) (keeps endpoints stable) ￼.

Deferred (not in MVP)
	•	Variables / assignments / “watch a constant”
	•	Nested functions (e.g., outer.inner)
	•	Fuzzy matching (similarity / edit distance / heuristics)
	•	Cross-language (Java/Go) parsing
	•	“Docstring-only change is cosmetic” nuance (in v1, docstring edits count as CONTENT unless you explicitly normalize them out)
	•	Persistent indexing cache across runs (MVP uses in-memory caching during a scan)

⸻

Design Decisions (Revised)

1) User specifies constructs via explicit FQN format

FQN format (explicit, stable):

relative/path/to/file.py::QualName

Where QualName uses dot-separated Python qualname rules for classes/methods:
	•	top-level function: src/foo.py::do_thing
	•	class: src/foo.py::Address
	•	method: src/foo.py::Address.validate_street

This directly addresses the review feedback requesting a clear FQN format.

2) Unified model: extend Subscription with optional semantic

Rationale:
	•	The repo already has a single Subscription dataclass with JSON serialization (to_dict/from_dict).
	•	The config JSON schema already stores subscriptions as a list; adding an optional field is the least disruptive change.

3) Simplest valuable fingerprinting (MVP)

We implement two hashes as required, but keep normalization simple:
	•	interface_hash (rename-resistant):
	•	includes: kind + normalized signature (parameters + return annotation if available) + decorators (and for classes: bases)
	•	excludes construct name and container names (so renames/moves don’t break)
	•	body_hash:
	•	derived from tree-sitter leaf tokens in the construct body
	•	ignores:
	•	comments
	•	whitespace/formatting
	•	includes:
	•	identifiers, keywords, literals, operators, etc.

This means formatting/comment-only edits won’t change body_hash, aligning with “COSMETIC → NO action”.

We also add fingerprint_version=1 to allow upgrading the hashing algorithm later without breaking old subs.

4) Parse errors policy (MVP)

When adding a semantic subscription:
	•	If the construct can’t be found (including because the file is too broken to parse), fail the command with a clear message.
	•	Suggest fallback: “use a line-range subscription instead”.

When scanning:
	•	If a target file parses with errors and we can’t reliably resolve the construct:
	•	Create a trigger with change_type="PARSE_ERROR" (so users know scan results are unreliable)
	•	Do not emit LOCATION proposals in this uncertain state (avoid wrong auto-updates)

⸻

User Interface

CLI

A) Create a semantic subscription
Keep the existing add command and extend what the location positional can accept.

# Existing (line-based) – unchanged:
codesub add src/codesub/models.py:42-50 --label "models chunk"

# New (semantic):
codesub add src/app/address.py::Address.validate_street --label "street validation"

Why this solves UX:
	•	It’s one command users already know (add)
	•	The target format is explicit and memorable (:: is the differentiator)

This matches current CLI shape (argparse subcommand add, with positional location) ￼.

B) Discover valid targets (addresses “unclear UX”)
Add a new command:

codesub symbols src/app/address.py
codesub symbols src/app/address.py --kind method
codesub symbols src/app/address.py --grep validate --json
codesub symbols src/app/address.py --ref HEAD~5

Output (human):

src/app/address.py::Address                    class  (10-120)
src/app/address.py::Address.validate_street    method (45-77)
src/app/address.py::normalize_street           function (5-8)

C) List subscriptions
Keep codesub list unchanged, but enhance display:
	•	For semantic subscriptions, show Target: path::qualname (kind)
	•	For line-based, show current line range

cmd_list already uses format_subscription(sub, verbose=args.verbose) ￼; we’ll update that formatter to include semantic info.

⸻

REST API

A) Keep existing endpoints stable
Current creation endpoint parses request.location using parse_location ￼. We will:
	•	Replace with parse_target_spec() that accepts either:
	•	path:start-end (line)
	•	path::qualname (semantic)

So:

POST /api/subscriptions
{
  "location": "src/app/address.py::Address.validate_street",
  "label": "street validation",
  "description": "",
  "context": 2
}

B) Add an endpoint to list symbols (optional but high UX value)
Add:
	•	GET /api/symbols?path=src/app/address.py&ref=baseline&kind=method&grep=validate

And a project-scoped version to match the existing project patterns:
	•	GET /api/projects/{project_id}/symbols?...

This mirrors existing project endpoints structure (e.g., project scan endpoints already exist) ￼.

⸻

Data Model Changes

1) Extend Subscription with an optional semantic target

Subscription today has fields like path, start_line, end_line, anchors, and JSON serialization methods.

Add this in src/codesub/models.py:

# src/codesub/models.py

from dataclasses import dataclass
from typing import Any

@dataclass
class SemanticTarget:
    language: str               # "python"
    kind: str                   # "class" | "function" | "method"
    qualname: str               # e.g. "Address.validate_street"
    interface_hash: str         # rename-resistant signature hash
    body_hash: str              # token-based body hash
    fingerprint_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "kind": self.kind,
            "qualname": self.qualname,
            "interface_hash": self.interface_hash,
            "body_hash": self.body_hash,
            "fingerprint_version": self.fingerprint_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticTarget":
        return cls(
            language=data["language"],
            kind=data["kind"],
            qualname=data["qualname"],
            interface_hash=data["interface_hash"],
            body_hash=data["body_hash"],
            fingerprint_version=data.get("fingerprint_version", 1),
        )

Then extend:

@dataclass
class Subscription:
    ...
    semantic: SemanticTarget | None = None

    def to_dict(self) -> dict[str, Any]:
        data = { ...existing fields... }
        if self.semantic is not None:
            data["semantic"] = self.semantic.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Subscription":
        semantic = None
        if data.get("semantic"):
            semantic = SemanticTarget.from_dict(data["semantic"])
        return cls(..., semantic=semantic)

2) Add change classification to triggers

Current Trigger has reasons and matching_hunks. Add:

change_type: str | None = None  # "STRUCTURAL"|"CONTENT"|"PARSE_ERROR"
details: dict[str, Any] | None = None

This enables API/CLI output to be explicit without stuffing everything into reasons.

3) Allow proposals to update semantic qualname on move/rename

Current Proposal has old/new path/lines + reasons + confidence.

Add:

new_qualname: str | None = None

So LOCATION proposals can update both file and symbol name.

4) Config schema versioning and backward compatibility

Config currently sets schema_version to 1 in Config.create() ￼ and ConfigStore enforces SCHEMA_VERSION = 1.

MVP plan:
	•	bump to SCHEMA_VERSION = 2
	•	allow loading v1 and migrating in-memory (so old repos still load)

⸻

Implementation Steps

Step 0 — Dependencies

Add Python dependencies (per research doc):
	•	tree-sitter
	•	tree-sitter-python ￼

Step 1 — New semantic parsing/indexing module

Create a new package:

src/codesub/semantic/
  __init__.py
  python_indexer.py

python_indexer.py responsibilities:
	•	parse source using tree-sitter (error-tolerant)
	•	extract constructs: class/function/method
	•	compute:
	•	start_line/end_line (1-based)
	•	qualname
	•	interface_hash/body_hash

Key types (MVP):

@dataclass(frozen=True)
class Construct:
    path: str
    kind: str          # "class"|"function"|"method"
    qualname: str
    start_line: int
    end_line: int
    interface_hash: str
    body_hash: str
    has_parse_error: bool

Implementation approach:
	•	Use tree-sitter queries (as in research doc) to capture function_definition, class_definition, and handle decorated_definition wrappers ￼.
	•	Build qualname:
	•	maintain a stack of surrounding classes while traversing
	•	classify “method” when function is inside a class body
	•	Fingerprinting:
	•	interface_hash = sha256 of canonical string:
	•	kind + normalized params + normalized decorators (+ bases for class)
	•	body_hash = sha256 of joined leaf token texts excluding comments

Step 2 — Parse “location or FQN” in one place

Add a new helper in src/codesub/utils.py (currently provides parse_location, used by CLI/API) ￼:

@dataclass(frozen=True)
class LineTarget:
    path: str
    start_line: int
    end_line: int

@dataclass(frozen=True)
class SemanticTargetSpec:
    path: str
    qualname: str

def parse_target_spec(spec: str) -> LineTarget | SemanticTargetSpec:
    if "::" in spec:
        path, qualname = spec.split("::", 1)
        if not path or not qualname:
            raise InvalidLocationError(spec, "expected 'path.py::QualName'")
        return SemanticTargetSpec(path=path, qualname=qualname)
    # fallback to existing line syntax
    path, start, end = parse_location(spec)
    return LineTarget(path=path, start_line=start, end_line=end)

Step 3 — CLI: extend cmd_add and add symbols

A) Update cmd_add (src/codesub/cli.py)
Today cmd_add:
	•	parses location with parse_location(args.location)
	•	reads file at baseline
	•	extracts anchors
	•	creates Subscription ￼

Update flow:
	•	target = parse_target_spec(args.location)
	•	If LineTarget: keep existing logic untouched
	•	If SemanticTargetSpec:
	•	read baseline file repo.show_file(baseline, path) (already done today)
	•	index constructs, find qualname
	•	use construct lines to extract anchors
	•	create subscription with semantic=SemanticTarget(...)

B) Add codesub symbols subcommand
In create_parser() (src/codesub/cli.py), add:
	•	symbols subparser with:
	•	positional path
	•	--ref default baseline
	•	--kind filter
	•	--grep filter
	•	--json

Step 4 — API: accept semantic FQN in location

In src/codesub/api.py, the create endpoint currently:
	•	path, start_line, end_line = parse_location(request.location) ￼

Replace with parse_target_spec and the same branch logic as CLI.

Also update response model conversion subscription_to_schema so it includes semantic info (new optional fields).

Step 5 — Detector: semantic detection path

Detector.scan currently:
	•	diffs base vs target
	•	rename/deleted detection via parse_name_status
	•	overlap hunks → Trigger
	•	else proposals for shift/rename → Proposal ￼

Add semantic branch inside the loop:

for sub in active_subs:
    if sub.semantic is not None:
        trig, prop = self._check_semantic(sub, base_ref, target_ref, rename_map, status_map)
        ...
        continue

    # existing line-based behavior unchanged

Add Detector._check_semantic(...) implementing the 2-stage pipeline:
	•	Stage 1:
	•	resolve file rename via rename_map.get(sub.path, sub.path) (same pattern used today) ￼
	•	try to locate qualname in that file at target ref
	•	compare interface/body hashes between base and target
	•	Stage 2:
	•	if not found by FQN, scan constructs in changed .py files in target ref, look for exact fingerprint match
	•	if exactly one match, create Proposal with:
	•	new_path/new_start/new_end
	•	new_qualname=match.qualname
	•	reasons=["semantic_location"]
	•	confidence="high"

Step 6 — Apply updates: update semantic qualname too

Update src/codesub/updater.py (not shown in the excerpt but used by CLI via apply-updates) to:
	•	apply proposal.new_qualname to sub.semantic.qualname when present
	•	also update path/line range as today

Step 7 — Output formatting (CLI + update docs)
	•	Update format_subscription to show semantic targets (CLI list) ￼
	•	Update update_doc.result_to_dict to include:
	•	trigger change_type
	•	proposal new_qualname
(Scan history stores result_dict = result_to_dict(result) already) ￼

⸻

Testing Strategy

Unit tests (pytest)

Create tests for:
	1.	Target parsing

	•	"a.py:1-2" → LineTarget
	•	"a.py::Foo.bar" → SemanticTargetSpec
	•	invalid forms → InvalidLocationError (existing error type) ￼

	2.	Python indexer extraction

	•	file with:
	•	one class, one method, one top-level function
	•	verify:
	•	FQN/qualname formation
	•	start/end lines
	•	kind classification

	3.	Fingerprint stability

	•	formatting-only change → same body_hash
	•	comment-only change → same body_hash
	•	signature change → different interface_hash
	•	body code change → different body_hash

	4.	Detector semantic classification

	•	STRUCTURAL trigger when interface hash differs
	•	CONTENT trigger when body hash differs
	•	LOCATION proposal when moved/renamed but hashes identical
	•	COSMETIC no trigger when only formatting/comments changed

	5.	Ambiguity behavior

	•	duplicate constructs with identical hashes in changed files → semantic_ambiguous_match trigger (no proposal)

Integration-style tests
	•	Initialize repo, baseline, add semantic sub, make commit that renames method, run scan:
	•	expect proposal with new_qualname
	•	Apply updates:
	•	expect subscription’s semantic target updated

⸻

Edge Cases
	1.	File deleted

	•	If status map says "D" for subscription path (same as current logic) ￼:
	•	semantic subscription emits a STRUCTURAL trigger (reasons=["file_deleted"])
	•	no proposal

	2.	Construct deleted

	•	File exists but symbol not found in target AND no stage2 fingerprint match:
	•	emit STRUCTURAL trigger (reasons=["semantic_target_missing"])

	3.	Syntax errors / malformed code

	•	If target file has parse errors and we can’t confidently locate symbol:
	•	emit PARSE_ERROR trigger
	•	include details like { "path": "...", "ref": "...", "note": "tree-sitter parse contained errors" }
	•	do not propose location updates (avoid bad auto-matches)

	4.	Multiple matches (ambiguous rename/move)

	•	stage2 finds >1 fingerprint match:
	•	emit STRUCTURAL trigger (reasons=["semantic_ambiguous_match"])
	•	include candidate FQNs in details to help user manually re-subscribe

	5.	Working directory scan

	•	If target_ref is None (already supported by scan flow) ￼:
	•	semantic indexer reads target file from disk
	•	base file still read from git show base_ref:path

⸻

Future Work (Deferred)
	•	Add variables/constants and assignment targets as subscribable constructs
	•	Support nested qualnames (Outer.inner) robustly
	•	Add fuzzy matching stage (e.g., match on interface_hash only, then rank by token similarity)
	•	Language plugins (Java/Go) using the same SemanticTarget(language=...) model
	•	Configurable “docstring-only changes are cosmetic”
	•	Persistent, incremental indexing cache (speed for large repos)

⸻


-------- USER INPUT -------- 
I want to specifically focus on:

Variables change
Constant value change

Field/function of a class deleted/renamed/changed type/changed default value

-------- END OF USER INPUT -------


Below is a focused revision of the semantic-subscriptions plan that prioritizes exactly what you listed:
	•	Variables change
	•	Constant value change
	•	Class field / class function (method) deleted / renamed / changed type / changed default value

It’s written to fit the current codesub architecture (single Subscription, JSON config, detector scan loop, argparse CLI, FastAPI CRUD).  ￼

⸻

Revised Implementation Plan: Semantic Subscriptions Focused on Variables, Constants, and Class API

MVP Scope

Included (MVP)

Python-only semantic targets, specifically:
	1.	Module variables / constants
	•	FOO = ...
	•	FOO: int = ...
	•	“Constant” is heuristic: ^[A-Z][A-Z0-9_]*$ (plus optional Final[...] detection).
	2.	Class fields (class-scope attributes / dataclass-style fields)
	•	class C: x = 1
	•	class C: x: int = 1
	•	class C: x: int (no default)
	3.	Class functions (methods)
	•	class C: def m(...): ...
	•	Track signature changes including type annotations and default values.

Change detection guarantees in MVP:
	•	Deleted target → TRIGGER
	•	Renamed / moved → PROPOSAL update (and if it also changed type/default/value/body, still TRIGGER)
	•	Type annotation changed → STRUCTURAL TRIGGER
	•	Default value changed (field default or function param default) → TRIGGER
	•	Constant value changed → TRIGGER

Backwards compatibility
	•	Existing line-range subscriptions remain unchanged and continue using diff-hunk overlap logic.  ￼

Deferred (explicitly not in MVP)
	•	Instance attributes (e.g., self.x = ... in __init__)
	•	Local variables inside functions
	•	Fuzzy similarity matching (edit distance / token similarity)
	•	“Semantic type change” without annotations (inference)
	•	Multi-language parsing (Java/Go)

⸻

Design Decisions (Revised for Your Focus)

1) Unified model: extend Subscription with optional semantic

Do not create a separate model. Keep a single list in config and add an optional semantic payload. This matches the repo patterns (Subscription.to_dict/from_dict, JSON config).  ￼

2) FQN format supports variables + class fields + methods

Primary format (what users type):

path/to/file.py::QualName

Where:
	•	Module var/const: src/settings.py::MAX_RETRIES
	•	Class field: src/models.py::User.role
	•	Method: src/models.py::User.save

Disambiguation format (only when needed):

path/to/file.py::kind:QualName

Kinds in MVP:
	•	variable (module scope)
	•	const (alias of variable, just sets “role” = constant)
	•	field (class scope)
	•	method

Examples:
	•	src/a.py::field:Config.TIMEOUT
	•	src/a.py::method:Config.validate

Reason: in Python you can have collisions (e.g., class and constant share the same name). This keeps the common case simple but still precise.

3) Fingerprinting tuned for “type/default/value changes”

For your focus, fingerprints must directly reflect:
	•	field type annotation changes
	•	method signature changes (type + defaults)
	•	constant/variable value changes

So:
	•	interface_hash = type-ish surface
	•	variables/fields: annotation tokens (or <no-annotation>)
	•	methods: full signature surface including parameter kinds/names, annotations, defaults, return annotation, decorators
	•	body_hash = value/body surface
	•	variables/fields: RHS expression tokens (or <no-default>)
	•	methods: body tokens (excluding comments/whitespace)

All tokens are derived from Tree-sitter leaf nodes, skipping comments/whitespace → formatting-only changes become COSMETIC.

4) Rename detection must still work when type/default/value changes

This is the big adjustment vs the earlier “hashes must both match”.

In MVP we still keep “Stage 1 + Stage 2”, but Stage 2 is hash-based candidate matching with strict uniqueness, not fuzzy similarity:
	•	Stage 1: exact match by stored (path, kind, qualname)
	•	Stage 2: if missing at target, search candidates (in changed .py files):
	1.	match on (interface_hash, body_hash)  → rename-only
	2.	else match on (body_hash) only         → rename + signature/type change but same body/value
	3.	else match on (interface_hash) only    → rename + body/value change but same signature/type

Only accept a candidate set if it yields exactly one match; otherwise mark ambiguous and do not auto-update.

This gives you rename detection even when the method/field also changed, without implementing fuzzy matching.

⸻

User Interface

CLI

Subscribe (existing command, extended)
Keep codesub add and expand the location syntax:

# Module constant/value tracking
codesub add src/settings.py::MAX_RETRIES --label "max retries"

# Class field default tracking
codesub add src/models.py::User.role --label "user role default"

# Method signature tracking (types + defaults)
codesub add src/models.py::User.save --label "User.save signature"

If ambiguous:

codesub add src/a.py::field:Config.TIMEOUT
codesub add src/a.py::const:TIMEOUT

Discover targets (new command)

codesub symbols src/models.py
codesub symbols src/models.py --kind field
codesub symbols src/models.py --kind method --grep save

Output example:

src/models.py::User.role            field   type=str   default="user"
src/models.py::User.save            method  (self, path: str = "tmp") -> None
src/settings.py::MAX_RETRIES        const   type=int   value=5

This solves the “how does a user create semantic subscriptions” UX issue.

⸻

REST API

Keep existing endpoints and extend location parsing the same way the CLI does. Today API assumes parse_location() always returns line ranges. We replace/extend that logic.  ￼
	•	POST /api/subscriptions and POST /api/projects/{project_id}/subscriptions
	•	accept:
	•	path:1-10 (existing)
	•	path::QualName (new semantic)

Optional (nice-to-have) for UX parity:
	•	GET /api/symbols?path=...&kind=field&grep=...

⸻

Data Model Changes

All changes are additive and preserve current config shape.  ￼

src/codesub/models.py

Add:

@dataclass
class SemanticTarget:
    language: str           # "python"
    kind: str               # "variable"|"field"|"method"
    qualname: str           # "MAX_RETRIES" | "User.role" | "User.save"
    role: str | None = None # "const" for constants, else None

    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1

Extend Subscription:

@dataclass
class Subscription:
    ...
    semantic: SemanticTarget | None = None

Update to_dict/from_dict to include semantic if present.

Triggers + Proposals should carry semantic info

Right now the detector only returns a trigger or a proposal per subscription (trigger short-circuits proposals). For your focus, a rename + type/default change should create:
	•	a proposal (update the subscription’s target to follow the rename)
	•	and a trigger (notify about the type/default change)

So extend models:

@dataclass
class Trigger:
    ...
    change_type: str | None = None   # "STRUCTURAL"|"CONTENT"|"MISSING"|"AMBIGUOUS"|"PARSE_ERROR"
    details: dict[str, Any] | None = None

@dataclass
class Proposal:
    ...
    new_qualname: str | None = None
    new_kind: str | None = None

This is still compatible: existing line-based triggers/proposals can leave these fields None.

⸻

Implementation Steps

1) Add a semantic indexer for Python variables/fields/methods

Create:

src/codesub/semantic/python_indexer.py

Responsibilities:
	•	Parse code with Tree-sitter (tolerant to errors)
	•	Extract constructs with:
	•	kind: variable/field/method
	•	qualname
	•	line range (for anchors / display)
	•	interface/body hashes

Extraction rules (MVP):
	•	Track module-scope assignments as variables/constants
	•	Track class-scope assignments/annotated assignments as fields
	•	Track class functions as methods
	•	Ignore:
	•	inside-function locals
	•	self.x = ... instance attrs
	•	multi-target destructuring like a, b = ... (MVP skip)

Important edge-case handling:
	•	If NAME is assigned multiple times at module/class scope:
	•	treat the “definition” as the last occurrence in that scope (most reflective of effective value)
	•	when adding subscription, if duplicates exist: print a warning and show which line is tracked.

2) Parse target specs (line-range vs semantic)

Add helper in src/codesub/utils.py (or a new targets.py module) to replace direct parse_location() use.
	•	If string contains :: → semantic target spec
	•	Else → existing parse_location()

Use this in CLI cmd_add and API create endpoints.  ￼

3) CLI: extend cmd_add and add symbols

Modify src/codesub/cli.py:
	•	In cmd_add, branch:
	•	line target → existing behavior
	•	semantic target:
	•	load file at baseline (repo.show_file)
	•	index constructs
	•	resolve the requested qualname (+ optional kind)
	•	create subscription storing semantic hashes + line range + anchors (anchors remain useful for display)
	•	Add a symbols command that uses indexer on baseline (or --ref).

4) API: allow semantic location

Modify src/codesub/api.py:
	•	create_subscription and create_project_subscription:
	•	parse location as line-or-semantic
	•	for semantic: resolve symbol in baseline, compute anchors from its line range, store semantic payload
	•	Extend SubscriptionSchema to include optional semantic fields (language/kind/qualname/role)

5) Detector: implement semantic checks for your change types

Modify src/codesub/detector.py to branch per subscription:
	•	If sub.semantic is None → current line-diff logic unchanged  ￼
	•	Else → semantic pipeline:

Semantic pipeline (base_ref → target_ref):
	1.	Resolve file rename via rename_map (same as today uses for path rename proposals).  ￼
	2.	Try Stage 1: exact match by (path, kind, qualname)
	3.	If missing, Stage 2: hash-based candidate match across changed python files:
	•	exact (interface+body)
	•	else body-only
	•	else interface-only
	•	require unique match
	4.	Classification + outputs:
	•	If match found:
	•	If (path/qualname changed) → Proposal(... new_path/new_lines/new_qualname ...)
	•	Compare hashes:
	•	interface changed → Trigger(change_type="STRUCTURAL", reasons=["type_or_defaults_changed"])
	•	body changed      → Trigger(change_type="CONTENT", reasons=["value_or_body_changed"])
	•	neither changed   → no trigger
	•	If no match found:
	•	Trigger(change_type="MISSING", reasons=["semantic_target_missing"])
	•	If ambiguous:
	•	Trigger(change_type="AMBIGUOUS", reasons=["semantic_ambiguous_match"], details={"candidates":[...]})

Key behavioral change: semantic subs may produce both proposal and trigger.

6) Updater: apply new_qualname and refresh fingerprints when baseline advances

Even though updater code isn’t in the context pack, it exists and is used by CLI/API.  ￼

Update behavior:
	•	When applying proposal for a semantic subscription:
	•	update sub.path, start_line, end_line
	•	update sub.semantic.qualname if new_qualname present
	•	After updating baseline to target_ref, refresh stored semantic hashes by re-indexing the target ref and rewriting interface_hash/body_hash (so next scan compares against the new baseline accurately).

⸻

Testing Strategy (focused on your scenarios)

Unit tests
	1.	Variable/constant extraction:

	•	module MAX_RETRIES = 5 → kind=variable, role=const
	•	change RHS 5 → 10 → CONTENT trigger

	2.	Field extraction:

	•	class User: role: str = "user"
	•	change annotation str → Literal["user","admin"] → STRUCTURAL trigger
	•	change default "user" → "admin" → CONTENT trigger (reason default_value_changed)

	3.	Method signature changes:

	•	param default change x=1 → x=2 → STRUCTURAL trigger
	•	annotation change x: int → x: float → STRUCTURAL trigger
	•	rename save → persist with same signature/body → proposal only
	•	rename + default change → proposal + STRUCTURAL trigger

	4.	Deleted / ambiguous:

	•	method removed → MISSING trigger
	•	two candidates share the same hash → AMBIGUOUS trigger, no proposal

Integration tests (git-based)
	•	Create repo history with:
	•	field rename + default change
	•	method rename + signature change
	•	constant moved file → proposal update

⸻

Edge Cases and How MVP Handles Them
	•	Multiple assignments to same name at module/class scope:
	•	indexer uses last assignment; warn at subscribe time.
	•	No annotation present:
	•	type changes can’t be detected unless an annotation is added/removed; interface_hash uses <no-annotation>.
	•	No default present (x: int):
	•	body_hash uses <no-default>. Adding/removing a default triggers CONTENT.
	•	Parse errors in target file:
	•	If tree-sitter parse errors prevent reliable symbol resolution:
	•	Trigger PARSE_ERROR
	•	Do not generate proposals (avoid wrong rename updates).
	•	Deleted file:
	•	Trigger reason file_deleted (consistent with current detector semantics).  ￼

⸻

Future Work (Deferred, but directly relevant)
	•	Instance attributes (self.x) as fields (requires limited flow-sensitive analysis)
	•	Tracking variable type changes via type checker output (out of scope for “static only w/o runtime”, but possible via mypy/pyright integration later)
	•	“Rename + changed body + changed signature” stronger matching (still deterministic, but needs better ranking)

⸻

If you want, I can also sketch the exact Tree-sitter node handling for:
	•	assignment
	•	annotated_assignment
	•	function_definition + decorated_definition
so it’s implementable without spelunking the grammar too much.
