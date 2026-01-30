# Implementation Plan: Aggregate/Container Tracking

## Overview

Add `--include-members` flag to semantic subscriptions that tracks a container (class/enum) and triggers when ANY member changes. This feature allows users to subscribe to an entire class or enum and receive notifications when any field, method, or nested class within the container is modified, added, or removed.

**Target Usage:**
```bash
codesub add auth.py::User --include-members
codesub add auth.py::User --include-members --include-private
codesub add auth.py::User --include-members --no-track-decorators
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Store flags in `SemanticTarget`, not `Subscription` | Keeps semantic-specific configuration grouped together; these flags only make sense for semantic subscriptions |
| Default `include_private=False` | Private members (`_field`) are implementation details; users must opt-in to track them |
| Default `track_decorators=True` | Decorator changes often signal API changes and should trigger by default |
| Track nested classes as members | Nested classes are part of the container's interface and should be monitored |
| Module-level aggregation NOT supported | Out of scope; too broad and could create noisy subscriptions |
| Report only changed members | Reduces noise; include parent subscription reference so user knows which aggregate subscription triggered |
| Store baseline member fingerprints | Enables detection of new members added since subscription creation |
| Use new change type `AGGREGATE` | Distinguishes container triggers from single-construct triggers |
| Container subscriptions use full Stage 1/2/3 detection | Enables move/rename support via hash-based relocation; skipping Stage 2/3 would break cross-file detection and rename tracking |
| `--include-private` only affects Python | Python uses underscore convention for private members; Java uses visibility modifiers which we don't parse, so all Java members are always included |
| Frontend updates deferred | Frontend changes to display aggregate triggers are out of scope for this PR; will be addressed in a follow-up |
| Recapture baseline members on proposal apply | When applying proposals, baseline_members must be refreshed to reflect current state |
| Compare members by relative ID on rename | When container is renamed (e.g., User to UserAccount), compare members by stripping the container prefix to avoid false "all removed/added" noise |
| Python indexer must emit container constructs | Required for `find_construct()` to locate the container; currently only emits fields/methods |
| Pass indexed constructs to member checking | Avoid re-indexing the same file twice (once for Stage 1, once for member extraction) |
| Track container rename in trigger details | When Stage 2/3 finds a renamed container, set `renamed=True` and track old/new qualnames |

**User Requirements:**
- `--include-private`: Optional flag to include private members (disabled by default)
- `--no-track-decorators`: Optional flag to disable decorator change detection (enabled by default)
- Only class/enum constructs can use `--include-members`
- New member detection is required
- Changed members should include parent subscription reference
- Container move/rename must be supported (cross-file detection, qualname changes)

**Alternative Approaches Considered:**
- **Store member list in Subscription**: Rejected because it duplicates information already in SemanticTarget and grows storage
- **Separate `ContainerSubscription` model**: Rejected because it complicates the existing model hierarchy; flags on SemanticTarget are simpler
- **Dynamic member discovery only**: Rejected because we need to detect NEW members added since baseline, which requires storing the baseline member set
- **Skip Stage 2/3 for containers**: Rejected because it breaks move/rename support; containers need the same relocation logic as regular semantic subscriptions

## Prerequisites

- Familiarity with the existing `SemanticTarget` and `Subscription` models
- Understanding of the `_check_semantic()` detection flow in `detector.py`
- Tree-sitter indexer APIs (`index_file`, `find_construct`)

## Implementation Steps

### Step 1: Extend SemanticTarget Model

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/models.py`

**Changes:**
- Add `include_members: bool = False` field to `SemanticTarget`
- Add `include_private: bool = False` field to `SemanticTarget`
- Add `track_decorators: bool = True` field to `SemanticTarget`
- Add `baseline_members: dict[str, MemberFingerprint] | None = None` field to store member fingerprints at creation time
- Add `baseline_container_qualname: str | None = None` field to track the original container qualname for rename comparison
- Update `to_dict()` and `from_dict()` methods to serialize new fields

**Code:**
```python
@dataclass
class MemberFingerprint:
    """Fingerprint data for a container member at baseline."""
    kind: str
    interface_hash: str
    body_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "interface_hash": self.interface_hash,
            "body_hash": self.body_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemberFingerprint":
        return cls(
            kind=data["kind"],
            interface_hash=data["interface_hash"],
            body_hash=data["body_hash"],
        )


@dataclass
class SemanticTarget:
    """Semantic identifier for a code construct."""

    language: str
    kind: str
    qualname: str
    role: str | None = None
    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1
    # Container tracking flags
    include_members: bool = False
    include_private: bool = False
    track_decorators: bool = True
    # Baseline member fingerprints (only populated when include_members=True)
    # Keys are RELATIVE member IDs (e.g., "validate", not "User.validate")
    baseline_members: dict[str, MemberFingerprint] | None = None
    # Original container qualname at subscription creation (for rename detection)
    baseline_container_qualname: str | None = None
```

### Step 2: Add Container Validation Constant

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/models.py`

**Changes:**
- Add module-level constant defining valid container kinds per language

**Code:**
```python
# Valid container kinds that can use include_members
CONTAINER_KINDS: dict[str, set[str]] = {
    "python": {"class", "enum"},
    "java": {"class", "interface", "enum"},
}
```

### Step 3: Extend Python Indexer to Emit Container Constructs

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py`

**Changes:**
- Modify `_extract_classes()` to emit a `Construct` for the class itself (not just its members)
- For Enum subclasses, emit with `kind="enum"` instead of `kind="class"`
- Compute `interface_hash` for class from decorators and base classes
- Compute `body_hash` for class from the full class body

**Code:**
```python
def _extract_classes(
    self,
    root: tree_sitter.Node,
    source_bytes: bytes,
    path: str,
    has_errors: bool,
) -> list[Construct]:
    """Extract classes with their fields and methods."""
    constructs: list[Construct] = []

    for child in root.children:
        # Handle both plain class_definition and decorated classes
        class_node = None
        decorated_node = None
        if child.type == "class_definition":
            class_node = child
        elif child.type == "decorated_definition":
            decorated_node = child
            # Find the class_definition inside the decorated_definition
            for inner in child.children:
                if inner.type == "class_definition":
                    class_node = inner
                    break

        if class_node is None:
            continue

        class_name = self._get_name(class_node)
        if not class_name:
            continue

        # Get class body
        body = class_node.child_by_field_name("body")
        if not body:
            continue

        # --- NEW: Emit container construct for the class itself ---
        container_construct = self._parse_class_container(
            class_node, source_bytes, path, has_errors, decorated_node
        )
        if container_construct:
            constructs.append(container_construct)
        # --- END NEW ---

        for member in body.children:
            # Class field: x = value
            if member.type == "expression_statement":
                expr = member.children[0] if member.children else None
                if expr and expr.type == "assignment":
                    construct = self._parse_assignment(
                        expr, source_bytes, path, class_name, has_errors
                    )
                    if construct:
                        constructs.append(construct)

            # Method: def name(...): ...
            elif member.type == "function_definition":
                construct = self._parse_method(
                    member, source_bytes, path, class_name, has_errors
                )
                if construct:
                    constructs.append(construct)

            # Decorated method: @decorator def name(...): ...
            elif member.type == "decorated_definition":
                func = None
                for c in member.children:
                    if c.type == "function_definition":
                        func = c
                        break
                if func:
                    construct = self._parse_method(
                        func,
                        source_bytes,
                        path,
                        class_name,
                        has_errors,
                        decorated_node=member,
                    )
                    if construct:
                        constructs.append(construct)

            # --- NEW: Nested class ---
            elif member.type == "class_definition":
                nested_construct = self._parse_class_container(
                    member, source_bytes, path, has_errors, None, parent_qualname=class_name
                )
                if nested_construct:
                    constructs.append(nested_construct)
            elif member.type == "decorated_definition":
                nested_class = None
                for c in member.children:
                    if c.type == "class_definition":
                        nested_class = c
                        break
                if nested_class:
                    nested_construct = self._parse_class_container(
                        nested_class, source_bytes, path, has_errors, member, parent_qualname=class_name
                    )
                    if nested_construct:
                        constructs.append(nested_construct)
            # --- END NEW ---

    return constructs


def _parse_class_container(
    self,
    class_node: tree_sitter.Node,
    source_bytes: bytes,
    path: str,
    has_errors: bool,
    decorated_node: tree_sitter.Node | None = None,
    parent_qualname: str | None = None,
) -> Construct | None:
    """Parse class definition and emit a container Construct.

    Args:
        class_node: The class_definition node.
        source_bytes: Source code bytes.
        path: File path.
        has_errors: Whether the tree has parse errors.
        decorated_node: The decorated_definition wrapper if class is decorated.
        parent_qualname: Parent class qualname for nested classes.

    Returns:
        Construct for the class container, or None if parsing fails.
    """
    name = self._get_name(class_node)
    if not name:
        return None

    qualname = f"{parent_qualname}.{name}" if parent_qualname else name

    # Determine kind: check if it's an Enum subclass
    kind = "class"
    superclasses = class_node.child_by_field_name("superclasses")
    if superclasses:
        superclass_text = self._node_text(superclasses, source_bytes)
        # Check for Enum inheritance patterns
        if "Enum" in superclass_text or "IntEnum" in superclass_text or "StrEnum" in superclass_text:
            kind = "enum"

    # Get decorators
    decorators: list[str] = []
    if decorated_node:
        for child in decorated_node.children:
            if child.type == "decorator":
                decorators.append(self._node_text(child, source_bytes))

    # interface_hash: decorators + base classes (inheritance)
    bases_text = self._node_text(superclasses, source_bytes) if superclasses else ""
    interface_hash = compute_interface_hash(
        kind,
        annotation=bases_text,  # Use annotation field for inheritance
        decorators=decorators,
    )

    # body_hash: full class body
    body = class_node.child_by_field_name("body")
    body_hash = compute_body_hash(body, source_bytes) if body else ""

    use_node = decorated_node or class_node
    return Construct(
        path=path,
        kind=kind,
        qualname=qualname,
        role=None,
        start_line=use_node.start_point[0] + 1,
        end_line=use_node.end_point[0] + 1,
        interface_hash=interface_hash,
        body_hash=body_hash,
        has_parse_error=has_errors,
    )
```

### Step 4: Add Helper Function to Extract Container Members

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py`

**Changes:**
- Add `get_container_members()` method to `PythonIndexer`
- Method filters constructs by qualname prefix to find direct members only
- Accept optional `constructs` parameter to reuse already-indexed constructs

**Code:**
```python
def get_container_members(
    self,
    source: str,
    path: str,
    container_qualname: str,
    include_private: bool = False,
    constructs: list[Construct] | None = None,
) -> list[Construct]:
    """Get all direct members of a container construct.

    Args:
        source: Source code text.
        path: File path.
        container_qualname: Qualname of the container (e.g., "User").
        include_private: Whether to include private members (_prefixed).
        constructs: Optional pre-indexed constructs to avoid re-parsing.

    Returns:
        List of Construct objects that are direct members of the container.
    """
    if constructs is None:
        constructs = self.index_file(source, path)

    prefix = f"{container_qualname}."

    members = []
    for c in constructs:
        if c.qualname.startswith(prefix):
            member_name = c.qualname[len(prefix):]
            # Only include direct members (one level deep)
            if "." in member_name:
                continue  # Skip nested members' members
            # Filter private if requested
            if not include_private and member_name.startswith("_"):
                continue
            members.append(c)

    return members
```

### Step 5: Add Same Helper to Java Indexer

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py`

**Changes:**
- Add `get_container_members()` method to `JavaIndexer` with same signature
- Note: `include_private` parameter is accepted for API consistency but has no effect for Java (all members included)

**Code:**
```python
def get_container_members(
    self,
    source: str,
    path: str,
    container_qualname: str,
    include_private: bool = False,
    constructs: list[Construct] | None = None,
) -> list[Construct]:
    """Get all direct members of a container construct.

    Note: The include_private parameter only affects Python subscriptions
    (underscore naming convention). For Java, all members are always included
    since Java uses visibility modifiers (public/private/protected) which
    we do not parse. The parameter is accepted for API consistency.

    Args:
        source: Source code text.
        path: File path.
        container_qualname: Qualname of the container.
        include_private: Ignored for Java; accepted for API consistency.
        constructs: Optional pre-indexed constructs to avoid re-parsing.

    Returns:
        List of Construct objects that are direct members of the container.
    """
    if constructs is None:
        constructs = self.index_file(source, path)

    prefix = f"{container_qualname}."

    members = []
    for c in constructs:
        if c.qualname.startswith(prefix):
            member_name = c.qualname[len(prefix):]
            # Only include direct members (one level deep)
            if "." in member_name:
                continue  # Skip nested members' members
            # Note: No private filtering for Java - all members included
            members.append(c)

    return members
```

### Step 6: Add Indexer Protocol Method

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/semantic/indexer_protocol.py`

**Changes:**
- Add `get_container_members()` to the `SemanticIndexer` protocol

**Code:**
```python
from typing import Protocol

class SemanticIndexer(Protocol):
    def index_file(self, source: str, path: str) -> list[Construct]: ...
    def find_construct(
        self, source: str, path: str, qualname: str, kind: str | None = None
    ) -> Construct | None: ...
    def get_container_members(
        self,
        source: str,
        path: str,
        container_qualname: str,
        include_private: bool = False,
        constructs: list[Construct] | None = None,
    ) -> list[Construct]: ...
```

### Step 7: Extend CLI with Container Flags

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/cli.py`

**Changes:**
- Add `--include-members` flag to `add` subparser
- Add `--include-private` flag to `add` subparser
- Add `--no-track-decorators` flag to `add` subparser
- Update `_add_semantic_subscription()` to validate container kind and pass flags

**Code:**
```python
# In create_parser(), add to add_parser:
add_parser.add_argument(
    "--include-members",
    action="store_true",
    help="Track all members of a container (class/enum). Triggers on any member change."
)
add_parser.add_argument(
    "--include-private",
    action="store_true",
    help="Include private members (_prefixed) when using --include-members. Only affects Python."
)
add_parser.add_argument(
    "--no-track-decorators",
    action="store_true",
    help="Disable tracking decorator changes (default: track decorators)"
)
```

**In `_add_semantic_subscription()`:**
```python
from .models import CONTAINER_KINDS, MemberFingerprint

# After finding the construct:
include_members = getattr(args, 'include_members', False)
include_private = getattr(args, 'include_private', False)
track_decorators = not getattr(args, 'no_track_decorators', False)

baseline_members = None
baseline_container_qualname = None

if include_members:
    valid_kinds = CONTAINER_KINDS.get(language, set())
    if construct.kind not in valid_kinds:
        print(f"Error: --include-members only valid for container kinds: {', '.join(sorted(valid_kinds))}")
        print(f"'{construct.qualname}' is a {construct.kind}, not a container.")
        return 1

    # Store baseline container qualname for rename comparison
    baseline_container_qualname = construct.qualname

    # Capture baseline member fingerprints with RELATIVE member IDs
    baseline_members = {}
    # Reuse the constructs list from finding the container
    all_constructs = indexer.index_file(source, target.path)
    members = indexer.get_container_members(
        source, target.path, construct.qualname, include_private, constructs=all_constructs
    )
    for m in members:
        # Store by relative member ID (strip container prefix)
        relative_id = m.qualname[len(construct.qualname) + 1:]  # +1 for the dot
        baseline_members[relative_id] = MemberFingerprint(
            kind=m.kind,
            interface_hash=m.interface_hash,
            body_hash=m.body_hash,
        )

# Create SemanticTarget with new flags:
semantic = SemanticTarget(
    language=language,
    kind=construct.kind,
    qualname=construct.qualname,
    role=construct.role,
    interface_hash=construct.interface_hash,
    body_hash=construct.body_hash,
    include_members=include_members,
    include_private=include_private,
    track_decorators=track_decorators,
    baseline_members=baseline_members,
    baseline_container_qualname=baseline_container_qualname,
)
```

### Step 8: Extend Detector with Container Logic

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/detector.py`

**Changes:**
- Add `_check_container_members()` method for container-specific detection
- Modify `_check_semantic()` to delegate to `_check_container_members()` when `include_members=True` after ANY stage succeeds
- Container subscriptions use full Stage 1/2/3 detection for move/rename support
- Compare members by **relative member ID** to handle container renames correctly
- Create detailed trigger with `change_type="AGGREGATE"` and member change list
- Track container rename when Stage 2/3 finds a match with different qualname

**Code for `_check_container_members()`:**
```python
def _check_container_members(
    self,
    sub: Subscription,
    new_source: str,
    new_path: str,
    indexer: "SemanticIndexer",
    current_container: "Construct",
    constructs: list["Construct"],
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
        new_source, new_path, current_container_qualname, semantic.include_private, constructs=constructs
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
            # Note: We can't easily distinguish decorators_changed vs inheritance_changed
            # without more sophisticated parsing. Report as interface_changed.
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
    details = {
        "container_qualname": current_container_qualname,
        "baseline_container_qualname": baseline_container_qualname,
        "parent_subscription_id": sub.id,
        "container_changes": container_changes,
        "member_changes": member_changes,
        "members_added": members_added,
        "members_removed": members_removed,
    }

    reasons = []
    if container_changes.get("renamed"):
        reasons.append("container_renamed")
    if members_added:
        reasons.append("member_added")
    if members_removed:
        reasons.append("member_removed")
    if any(c["change_type"] == "STRUCTURAL" and c.get("reason") != "container_interface_changed" for c in member_changes):
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
```

**Integration in `_check_semantic()` - modify Stage 1 success block:**

```python
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
                    proposal = None

                    # Generate proposal if location changed (file rename or line shift)
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

                # Regular (non-container) semantic subscription
                trigger = self._classify_semantic_change(sub, new_construct)
                # ... rest of existing code ...
```

**Modify Stage 2 success block to handle containers:**

```python
            # Stage 2: Hash-based search in same file
            new_constructs = indexer.index_file(new_source, new_path)
            # Cache for potential reuse
            cache_key = (new_path, sub.semantic.language)
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
```

**Modify Stage 3 (cross-file) success block to handle containers:**

```python
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
```

### Step 9: Update Updater to Recapture Baseline Members

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/updater.py`

**Changes:**
- After updating subscription location, recapture `baseline_members` for container subscriptions
- Also update container's own `interface_hash`, `body_hash`, and `qualname` to reflect current state
- Update `baseline_container_qualname` to match the new qualname

**Code (add after the anchors update, within the `if not dry_run:` block):**
```python
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
                    from .semantic import get_indexer
                    from .models import MemberFingerprint

                    try:
                        indexer = get_indexer(sub.semantic.language)
                        source = "\n".join(new_lines)

                        # Determine the current qualname (may have changed via proposal)
                        current_qualname = getattr(p, 'new_qualname', None) or sub.semantic.qualname

                        # Find the container construct
                        all_constructs = indexer.index_file(source, new_path)
                        container = indexer.find_construct(
                            source, new_path, current_qualname, sub.semantic.kind
                        )
                        if container:
                            # Update container fingerprints and qualname
                            sub.semantic.interface_hash = container.interface_hash
                            sub.semantic.body_hash = container.body_hash
                            sub.semantic.qualname = current_qualname
                            sub.semantic.baseline_container_qualname = current_qualname

                        # Recapture member fingerprints with RELATIVE IDs
                        members = indexer.get_container_members(
                            source, new_path, current_qualname, sub.semantic.include_private, constructs=all_constructs
                        )
                        sub.semantic.baseline_members = {}
                        for m in members:
                            relative_id = m.qualname[len(current_qualname) + 1:]
                            sub.semantic.baseline_members[relative_id] = MemberFingerprint(
                                kind=m.kind,
                                interface_hash=m.interface_hash,
                                body_hash=m.body_hash,
                            )
                    except Exception:
                        # If recapture fails, log warning but don't fail the update
                        warnings.append(
                            f"Failed to recapture baseline members for {sub_id[:8]}"
                        )
```

### Step 10: Update API Schemas

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Add `include_members`, `include_private`, `track_decorators` to `SubscriptionCreateRequest`
- Add `include_members`, `include_private`, `track_decorators`, `baseline_members`, `baseline_container_qualname` to `SemanticTargetSchema`
- Update `subscription_to_schema()` helper

**Code:**
```python
class SubscriptionCreateRequest(BaseModel):
    location: str = Field(...)
    label: Optional[str] = None
    description: Optional[str] = None
    context: int = Field(default=2, ge=0, le=10)
    trigger_on_duplicate: bool = Field(default=False, ...)
    include_members: bool = Field(
        default=False,
        description="For containers (class/enum): track all members and trigger on any change"
    )
    include_private: bool = Field(
        default=False,
        description="Include private members (_prefixed) when using include_members. Only affects Python."
    )
    track_decorators: bool = Field(
        default=True,
        description="Track decorator changes on the container (when include_members=True)"
    )


class MemberFingerprintSchema(BaseModel):
    kind: str
    interface_hash: str
    body_hash: str


class SemanticTargetSchema(BaseModel):
    language: str
    kind: str
    qualname: str
    role: Optional[str] = None
    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1
    include_members: bool = False
    include_private: bool = False
    track_decorators: bool = True
    baseline_members: Optional[dict[str, MemberFingerprintSchema]] = None
    baseline_container_qualname: Optional[str] = None
```

### Step 11: Update _create_subscription_from_request in API

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/api.py`

**Changes:**
- Pass new flags to SemanticTarget creation
- Validate container kind and capture baseline members with relative IDs

**Code:**
```python
def _create_subscription_from_request(...) -> Subscription:
    # ... existing code ...

    if isinstance(target, SemanticTargetSpec):
        # ... existing construct lookup ...

        include_members = request.include_members
        include_private = request.include_private
        track_decorators = request.track_decorators
        baseline_members = None
        baseline_container_qualname = None

        if include_members:
            from .models import CONTAINER_KINDS, MemberFingerprint
            valid_kinds = CONTAINER_KINDS.get(language, set())
            if construct.kind not in valid_kinds:
                raise InvalidLocationError(
                    request.location,
                    f"--include-members only valid for: {', '.join(sorted(valid_kinds))}. "
                    f"'{construct.qualname}' is a {construct.kind}."
                )

            # Store baseline container qualname
            baseline_container_qualname = construct.qualname

            # Index file once and reuse
            all_constructs = indexer.index_file(source, target.path)
            members = indexer.get_container_members(
                source, target.path, construct.qualname, include_private, constructs=all_constructs
            )
            baseline_members = {}
            for m in members:
                # Store by relative member ID
                relative_id = m.qualname[len(construct.qualname) + 1:]
                baseline_members[relative_id] = MemberFingerprint(
                    kind=m.kind,
                    interface_hash=m.interface_hash,
                    body_hash=m.body_hash,
                )

        semantic = SemanticTarget(
            language=language,
            kind=construct.kind,
            qualname=construct.qualname,
            role=construct.role,
            interface_hash=construct.interface_hash,
            body_hash=construct.body_hash,
            include_members=include_members,
            include_private=include_private,
            track_decorators=track_decorators,
            baseline_members=baseline_members,
            baseline_container_qualname=baseline_container_qualname,
        )
        # ... rest of subscription creation ...
```

### Step 12: Update Subscription Display

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/utils.py`

**Changes:**
- Update `format_subscription()` to show container tracking status

**Code:**
```python
def format_subscription(sub: "Subscription", verbose: bool = False) -> str:
    # ... existing code ...

    # Add container indicator
    if sub.semantic and sub.semantic.include_members:
        member_count = len(sub.semantic.baseline_members or {})
        result += f" [container: {member_count} members]"
        if verbose:
            if sub.semantic.include_private:
                result += "\n         Include private: yes"
            if not sub.semantic.track_decorators:
                result += "\n         Track decorators: no"

    # ... rest of formatting ...
```

### Step 13: Update Update Document Format

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/update_doc.py`

**Changes:**
- Handle `AGGREGATE` change type in trigger formatting
- Include member change details in output

**Code:**
```python
def _format_trigger(trigger: Trigger) -> dict[str, Any]:
    result = {
        "subscription_id": trigger.subscription_id,
        "path": trigger.path,
        "start_line": trigger.start_line,
        "end_line": trigger.end_line,
        "reasons": trigger.reasons,
        "change_type": trigger.change_type,
    }

    if trigger.details:
        result["details"] = trigger.details

    if trigger.subscription.label:
        result["label"] = trigger.subscription.label

    return result
```

### Step 14: Add Error for Invalid Container Usage

**Files:** `/Users/vlad/dev/projects/codesub/src/codesub/errors.py`

**Changes:**
- Add `InvalidContainerError` exception class

**Code:**
```python
class InvalidContainerError(CodesubError):
    """Raised when --include-members is used on a non-container construct."""

    def __init__(self, qualname: str, kind: str, valid_kinds: set[str]) -> None:
        self.qualname = qualname
        self.kind = kind
        self.valid_kinds = valid_kinds
        super().__init__(
            f"'{qualname}' is a {kind}, not a container. "
            f"--include-members requires: {', '.join(sorted(valid_kinds))}"
        )
```

## Testing Strategy

### Unit Tests

Add tests to existing test files where appropriate to maintain test organization.

**File:** `/Users/vlad/dev/projects/codesub/tests/test_models.py` (add to existing)

- [ ] `test_member_fingerprint_serialization` - Verify MemberFingerprint to_dict/from_dict
- [ ] `test_semantic_target_container_flags_serialization` - Verify new fields serialize/deserialize correctly
- [ ] `test_container_kinds_constant` - Verify CONTAINER_KINDS has expected values
- [ ] `test_baseline_container_qualname_serialization` - Verify baseline_container_qualname serializes correctly

**File:** `/Users/vlad/dev/projects/codesub/tests/test_semantic_indexers.py` (add to existing or create)

- [ ] `test_python_indexer_emits_class_construct` - Verify Python indexer emits class/enum constructs
- [ ] `test_python_indexer_emits_enum_construct` - Verify Enum subclasses get kind="enum"
- [ ] `test_python_indexer_emits_nested_class_construct` - Verify nested classes are emitted
- [ ] `test_python_get_container_members_basic` - Verify Python indexer extracts class members
- [ ] `test_python_get_container_members_excludes_private_by_default` - Verify _prefixed members excluded
- [ ] `test_python_get_container_members_includes_private_when_requested` - Verify _prefixed members included with flag
- [ ] `test_python_get_container_members_direct_only` - Verify nested class members not included
- [ ] `test_python_get_container_members_reuses_constructs` - Verify constructs parameter avoids re-indexing
- [ ] `test_java_get_container_members_basic` - Verify Java indexer extracts class members
- [ ] `test_java_get_container_members_includes_all` - Verify include_private has no effect for Java
- [ ] `test_java_get_container_members_reuses_constructs` - Verify constructs parameter avoids re-indexing

### Integration Tests

**File:** `/Users/vlad/dev/projects/codesub/tests/test_detector.py` (add to existing)

- [ ] `test_container_unchanged_no_trigger` - Container with no changes remains unchanged
- [ ] `test_container_member_value_change_triggers` - Field value change triggers AGGREGATE
- [ ] `test_container_member_type_change_triggers` - Field type change triggers AGGREGATE (STRUCTURAL)
- [ ] `test_container_member_added_triggers` - New member triggers AGGREGATE
- [ ] `test_container_member_removed_triggers` - Deleted member triggers AGGREGATE
- [ ] `test_container_decorator_change_triggers` - Container decorator change triggers (default)
- [ ] `test_container_decorator_change_ignored_when_disabled` - No trigger when track_decorators=False
- [ ] `test_container_cosmetic_change_no_trigger` - Whitespace changes don't trigger
- [ ] `test_container_line_shift_creates_proposal` - Container moved creates proposal
- [ ] `test_container_renamed_same_file` - Container renamed (User -> UserAccount) creates proposal and correct member comparison
- [ ] `test_container_renamed_no_false_member_changes` - Rename doesn't report all members as added/removed
- [ ] `test_container_moved_cross_file` - Container moved to different file creates proposal and compares members correctly
- [ ] `test_container_moved_and_renamed` - Container moved AND renamed is handled correctly
- [ ] `test_container_deleted_returns_missing` - Container deleted returns MISSING trigger (after Stage 2/3 search fails)
- [ ] `test_container_hash_relocation_same_file` - Stage 2 hash search finds renamed container in same file
- [ ] `test_container_hash_relocation_cross_file` - Stage 3 cross-file search finds moved container

### CLI Tests

**File:** `/Users/vlad/dev/projects/codesub/tests/test_cli.py` (add to existing)

- [ ] `test_cli_add_include_members_flag` - Verify flag parsing
- [ ] `test_cli_add_include_private_flag` - Verify flag parsing
- [ ] `test_cli_add_no_track_decorators_flag` - Verify flag parsing
- [ ] `test_cli_add_include_members_on_method_fails` - Verify validation error
- [ ] `test_cli_add_include_members_stores_relative_member_ids` - Verify baseline_members uses relative IDs
- [ ] `test_cli_list_shows_container_status` - Verify display format

### API Tests

**File:** `/Users/vlad/dev/projects/codesub/tests/test_api.py` (add to existing)

- [ ] `test_api_create_container_subscription` - POST with include_members=true
- [ ] `test_api_create_container_subscription_invalid_kind` - Verify 400 error
- [ ] `test_api_get_container_subscription` - Verify schema includes new fields
- [ ] `test_api_scan_container_trigger` - Verify AGGREGATE trigger in scan response
- [ ] `test_api_scan_container_rename` - Verify renamed container produces correct trigger

### Updater Tests

**File:** `/Users/vlad/dev/projects/codesub/tests/test_updater.py` (add to existing)

- [ ] `test_updater_recaptures_baseline_members` - Verify baseline_members refreshed on apply
- [ ] `test_updater_updates_container_fingerprints` - Verify interface_hash/body_hash updated
- [ ] `test_updater_updates_container_qualname_on_rename` - Verify qualname and baseline_container_qualname updated
- [ ] `test_updater_recaptures_with_relative_ids` - Verify recaptured baseline_members uses relative IDs

## Edge Cases Considered

- **Empty container (class with no members):** Should work, just no member triggers. Container-level changes still tracked.
- **Single-member container:** Works normally, triggers on that one member change.
- **Deeply nested classes:** Only direct nested classes are members; their internal members are not tracked unless separately subscribed.
- **Constructor as member:** `__init__` is a method and tracked as a member.
- **Static methods and class methods:** Tracked as regular methods (their decorators affect interface_hash).
- **Properties:** Tracked as methods with `@property` decorator.
- **Enum values in Python:** Tracked as fields with special handling.
- **Private nested class:** `_InnerClass` excluded by default, included with `--include-private` (Python only).
- **Container not found anywhere (truly deleted):** Returns MISSING trigger after Stage 2/3 search fails.
- **Container renamed (qualname changed):** Detected via Stage 2 hash match. Members compared by relative ID to avoid false positives.
- **Container moved to different file:** Detected via Stage 3 cross-file search. Members compared correctly.
- **Container moved AND renamed:** Both detected; proposal includes new path and new_qualname.
- **Java private members:** All Java members included regardless of `include_private` flag since Java uses visibility modifiers.
- **Python indexer now emits class constructs:** Required fix for `find_construct()` to locate containers.

## Risks and Mitigations

- **Risk:** Large containers (50+ members) could slow down scans.
  **Mitigation:** Constructs are cached and passed to `get_container_members()` to avoid re-indexing. Member comparison is O(n) which is acceptable.

- **Risk:** Baseline member snapshot becomes stale if subscription is not updated after applying proposals.
  **Mitigation:** `updater.py` now recaptures `baseline_members` when applying proposals. Document this behavior.

- **Risk:** Hash collisions causing false negatives (missed changes).
  **Mitigation:** Use SHA-256 truncated to 16 hex chars. Collision probability is negligible for typical codebases.

- **Risk:** Nested class recursion issues.
  **Mitigation:** Only track direct members (one level deep via corrected logic). Document this limitation.

- **Risk:** Breaking change if existing subscriptions have unexpected baseline_members field.
  **Mitigation:** Field defaults to None and is only populated for new container subscriptions. Existing subscriptions are unaffected.

- **Risk:** Container rename causes false "all members removed/added" noise.
  **Mitigation:** Compare members by relative ID (strip container prefix). Track baseline_container_qualname separately.

- **Risk:** Double-indexing files (find_construct + get_container_members).
  **Mitigation:** Pass `constructs` parameter to reuse already-indexed list. Cache constructs in detector.

## Out of Scope

- **Frontend updates:** Changes to the React frontend to display aggregate triggers are deferred to a follow-up PR.
- **Module-level aggregation:** Tracking all constructs in a module is too broad and not supported.
- **Distinguishing decorator vs inheritance changes:** Both affect interface_hash; reported as "interface_changed" rather than separate flags.
