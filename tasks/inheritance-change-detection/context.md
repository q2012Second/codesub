# Context: Inheritance-Aware Change Detection

## Problem Summary
Implement inheritance-aware change detection: when a parent class changes, subscriptions on child classes (that inherit affected members) should be triggered.

**Requirements:**
- Full inheritance chain (grandparents, etc.)
- Cross-file inheritance support (requires import resolution)
- Only trigger for inherited members (not overridden)
- Automatic for all semantic subscriptions

---

## `/Users/vlad/dev/projects/codesub/src/codesub/semantic/construct.py` [FULL]
**Relevance:** Core dataclass representing a semantic code unit. May need to extend with base class information.
**Lines:** FULL

```python
"""Construct dataclass for semantic code analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Construct:
    """A parsed code construct.

    Represents a semantic unit extracted from source code, such as a
    class, method, field, or variable. Used for semantic subscriptions
    that track code by identity rather than line numbers.

    Attributes:
        path: File path where the construct is defined.
        kind: Type of construct. Valid values:
            - "variable": Module-level variable
            - "field": Class field or attribute
            - "method": Method or function within a class
            - "function": Module-level function (not inside a class)
            - "class": Class declaration
            - "interface": Interface declaration (Java)
            - "enum": Enum declaration
        qualname: Qualified name of the construct.
            - Simple: "MAX_RETRIES", "User", "create_order"
            - Nested: "User.role", "Calculator.add(int,int)"
            - Java overloads include param types: "add(int,int)"
        role: Optional role modifier.
            - "const": For constants (UPPER_CASE naming)
            - None: For regular constructs
        start_line: 1-based start line number (includes decorators if present).
        end_line: 1-based end line number (inclusive).
        definition_line: 1-based line of the actual definition (class/def keyword).
            For decorated constructs, this differs from start_line.
        interface_hash: Hash of the construct's interface/signature.
            Changes indicate structural changes (type annotations, parameters).
        body_hash: Hash of the construct's body/value.
            Changes indicate content changes (implementation, value).
        has_parse_error: True if the file had parse errors.
    """

    path: str
    kind: str  # "variable"|"field"|"method"|"function"|"class"|"interface"|"enum"
    qualname: str  # "MAX_RETRIES" | "User.role" | "User.save" | "User"
    role: str | None  # "const" for constants, else None
    start_line: int
    end_line: int
    definition_line: int  # Line of actual class/def keyword (differs from start_line if decorated)
    interface_hash: str
    body_hash: str
    has_parse_error: bool = False
```

**TODO for inheritance:**
- Add `base_classes: list[str] | None` field to track inheritance
- Consider storing qualified base class names (not just simple names)

---

## `/Users/vlad/dev/projects/codesub/src/codesub/semantic/python_indexer.py` [EXCERPT]
**Relevance:** Extracts constructs from Python code. Already extracts base class info in `_parse_class_container` but doesn't store it.
**Lines:** 410-481 (class parsing), 483-521 (get_container_members)

```python
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
        if any(
            enum_type in superclass_text
            for enum_type in ("Enum", "IntEnum", "StrEnum", "Flag", "IntFlag")
        ):
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
        definition_line=class_node.start_point[0] + 1,  # Actual class line, not decorator
        interface_hash=interface_hash,
        body_hash=body_hash,
        has_parse_error=has_errors,
    )

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
            member_name = c.qualname[len(prefix) :]
            # Only include direct members (one level deep)
            if "." in member_name:
                continue  # Skip nested members' members
            # Filter private if requested
            if not include_private and member_name.startswith("_"):
                continue
            members.append(c)

    return members
```

**Current base class extraction:**
- Line 440: `superclasses = class_node.child_by_field_name("superclasses")`
- Line 442: `superclass_text = self._node_text(superclasses, source_bytes)` (e.g., "User, Mixin")
- Currently only used for: (1) detecting Enum pattern, (2) hashing in interface_hash
- **Does NOT parse into individual base class names or store them**

**TODO for inheritance:**
- Parse `superclass_text` to extract individual base class names
- Store base class list in Construct (when added)
- Handle multiple inheritance (Python supports this)

---

## `/Users/vlad/dev/projects/codesub/src/codesub/semantic/java_indexer.py` [EXCERPT]
**Relevance:** Java indexer with similar base class extraction pattern.
**Lines:** 99-170 (class extraction)

```python
def _extract_class(
    self,
    node: tree_sitter.Node,
    source_bytes: bytes,
    path: str,
    has_errors: bool,
    scope: list[str],
    kind: str,
) -> list[Construct]:
    """Extract class/interface declaration and its members."""
    constructs: list[Construct] = []

    name = self._get_name(node)
    if not name:
        return constructs

    qualname = ".".join(scope + [name])

    # Get decorators (annotations)
    decorators = self._get_annotations(node, source_bytes)

    # Get modifiers and superclass/interfaces for interface_hash
    modifiers = self._get_modifiers(node, source_bytes)
    superclass = node.child_by_field_name("superclass")
    interfaces = node.child_by_field_name("interfaces")

    annotation_text = None
    parts = []
    if superclass:
        parts.append(f"extends {self._node_text(superclass, source_bytes)}")
    if interfaces:
        parts.append(self._node_text(interfaces, source_bytes))
    if parts:
        annotation_text = " ".join(parts)

    interface_hash = compute_interface_hash(
        kind,
        annotation=annotation_text,
        decorators=modifiers + decorators,
    )

    # Body hash includes the class signature but not members
    # For class detection, use the class header as body
    body_hash = compute_body_hash(None, source_bytes)

    constructs.append(
        Construct(
            path=path,
            kind=kind,
            qualname=qualname,
            role=None,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            definition_line=node.start_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )
    )

    # Process class body for members
    body = node.child_by_field_name("body")
    if body:
        new_scope = scope + [name]
        for child in body.children:
            constructs.extend(
                self._extract_declaration(
                    child, source_bytes, path, has_errors, new_scope
                )
            )

    return constructs
```

**Current base class extraction:**
- Line 122: `superclass = node.child_by_field_name("superclass")` (single parent in Java)
- Line 123: `interfaces = node.child_by_field_name("interfaces")` (multiple interfaces)
- Currently only used for hashing in interface_hash
- **Does NOT parse or store individual base class/interface names**

**TODO for inheritance:**
- Extract superclass name (strip "extends" keyword)
- Parse interfaces list into individual names
- Store in Construct base_classes field

---

## `/Users/vlad/dev/projects/codesub/src/codesub/detector.py` [EXCERPT]
**Relevance:** Main detection logic. Container member checking shows the pattern we need to extend.
**Lines:** 634-783 (_check_container_members function)

```python
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
```

**Key pattern:**
- Compares baseline member fingerprints with current members
- Uses relative IDs for comparison (enables container renames)
- Detects ADDED, MISSING, STRUCTURAL, CONTENT changes
- Aggregates all changes into single AGGREGATE trigger

**TODO for inheritance:**
- Add new function: `_check_inherited_member_changes(sub, parent_constructs, file_diffs, ...)`
- For each child class subscription, find parent classes (requires inheritance chain resolution)
- For each parent class changed in diff, check if child inherits affected members
- Filter out overridden members (child has same relative_id)
- Generate AGGREGATE triggers with inherited member changes

---

## `/Users/vlad/dev/projects/codesub/src/codesub/models.py` [EXCERPT]
**Relevance:** Data models. SemanticTarget already has container tracking fields.
**Lines:** 50-116 (SemanticTarget)

```python
@dataclass
class SemanticTarget:
    """Semantic identifier for a code construct."""

    language: str  # "python"
    kind: str  # "variable"|"field"|"method"|"class"|"interface"|"enum"
    qualname: str  # "MAX_RETRIES" | "User.role" | "User.save" | "User"
    role: str | None = None  # "const" for constants, else None
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

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "language": self.language,
            "kind": self.kind,
            "qualname": self.qualname,
            "role": self.role,
            "interface_hash": self.interface_hash,
            "body_hash": self.body_hash,
            "fingerprint_version": self.fingerprint_version,
        }
        # Only include container fields if include_members is True
        if self.include_members:
            result["include_members"] = self.include_members
            result["include_private"] = self.include_private
            result["track_decorators"] = self.track_decorators
            if self.baseline_members is not None:
                result["baseline_members"] = {
                    k: v.to_dict() for k, v in self.baseline_members.items()
                }
            if self.baseline_container_qualname is not None:
                result["baseline_container_qualname"] = self.baseline_container_qualname
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticTarget":
        baseline_members = None
        if "baseline_members" in data and data["baseline_members"] is not None:
            baseline_members = {
                k: MemberFingerprint.from_dict(v)
                for k, v in data["baseline_members"].items()
            }
        return cls(
            language=data["language"],
            kind=data["kind"],
            qualname=data["qualname"],
            role=data.get("role"),
            interface_hash=data.get("interface_hash", ""),
            body_hash=data.get("body_hash", ""),
            fingerprint_version=data.get("fingerprint_version", 1),
            include_members=data.get("include_members", False),
            include_private=data.get("include_private", False),
            track_decorators=data.get("track_decorators", True),
            baseline_members=baseline_members,
            baseline_container_qualname=data.get("baseline_container_qualname"),
        )
```

**TODO for inheritance:**
- Consider adding `track_inherited_members: bool = True` flag (default enabled)
- This would allow users to opt-out of inheritance tracking if needed
- No need to store inheritance chain in SemanticTarget (can be recomputed)

---

## `/Users/vlad/dev/projects/codesub/tests/test_container_tracking.py` [EXCERPT]
**Relevance:** Shows Admin(User) inheritance example at line 64-72. Test patterns for member changes.
**Lines:** 41-72 (test fixture), 248-283 (member change test)

```python
CONTAINER_BASE = '''"""Container tracking test module."""

class User:
    """User model."""

    name: str = ""
    email: str = ""
    _secret: str = "hidden"

    def validate(self) -> bool:
        """Validate user data."""
        return bool(self.name and self.email)

    def _internal_check(self) -> bool:
        """Internal validation."""
        return True

    @property
    def display_name(self) -> str:
        """Get display name."""
        return self.name.title()


class Admin(User):
    """Admin user."""

    role: str = "admin"

    def can_edit(self, resource: str) -> bool:
        """Check edit permission."""
        return True
'''

# ... later in tests ...

class TestMemberContentChange:
    """Test member body/value changes (CONTENT)."""

    def test_method_body_change_triggers(self, container_repo: Path):
        """Changing method body triggers AGGREGATE with member_body_changed."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Modify method body
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name and self.email and len(self.name) > 1)"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change validate body")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_body_changed" in trigger.reasons
        assert trigger.details is not None
        # Check member_changes
        member_changes = trigger.details["member_changes"]
        assert len(member_changes) == 1
        assert member_changes[0]["relative_id"] == "validate"
        assert member_changes[0]["change_type"] == "CONTENT"
```

**Key insight:**
- Admin(User) is already in test fixture but inheritance is NOT currently tracked
- If User.validate() changes, Admin subscription should ALSO trigger (since Admin inherits validate)
- Need test: "Change User.validate, expect Admin subscription to trigger with inherited_member_changed"

---

## Key Implementation Challenges

### 1. **Inheritance Chain Resolution**
- Need to resolve base class names to actual Construct objects
- **Same-file**: Easy - look up in current constructs list by qualname
- **Cross-file**: Hard - requires import resolution
  - Parse import statements (from X import Y, import X)
  - Map imported names to file paths
  - Index target file to get base class Construct
  - Handle transitive inheritance (grandparents)

### 2. **Detecting Which Members Are Inherited**
```python
class User:
    def validate(self): ...

class Admin(User):
    role: str = "admin"  # NOT inherited, unique to Admin
    # validate is inherited from User (not overridden)
```

Algorithm:
1. Get all members of child class: `["role", "validate"]`
2. Get baseline members of child (only direct members): `{"role": ...}`
3. Inherited members = members NOT in baseline: `["validate"]`
4. Check if parent's `validate` changed -> trigger child subscription

### 3. **Avoiding Duplicate Triggers**
- If User subscription exists: trigger for User
- If Admin subscription exists: trigger for Admin (inherited change)
- Both should trigger independently

### 4. **Performance**
- Inheritance checking requires indexing multiple files
- Could be expensive in large codebases
- Need caching strategy (construct_cache already exists in detector)

---

## Recommended Approach

### Phase 1: Basic Same-File Inheritance
1. Add `base_classes: list[str] | None` to Construct
2. Update PythonIndexer._parse_class_container to parse and store base classes
3. Update JavaIndexer._extract_class to parse and store base classes
4. In detector._check_semantic, after checking direct members:
   - If subscription is a container with base classes in same file
   - For each base class that changed in diff
   - Check if child inherits affected members
   - Generate inherited member change trigger

### Phase 2: Cross-File Inheritance (Future)
1. Add import parsing to indexers
2. Build import -> file path mapping
3. Resolve cross-file base classes
4. Extend Phase 1 logic to handle cross-file parents

### Phase 3: Transitive Inheritance (Future)
1. Build full inheritance tree (BFS/DFS)
2. Check all ancestors for changes
3. Attribute changes to immediate parent for clarity

---

## Test Plan

### Same-File Tests
1. `test_inherited_method_change_triggers_child_subscription`
   - Subscribe to Admin class
   - Change User.validate() body
   - Expect Admin subscription to trigger with inherited_member_body_changed
2. `test_overridden_method_change_does_not_trigger_child`
   - Admin overrides validate()
   - Change User.validate()
   - Admin subscription should NOT trigger (has its own version)
3. `test_grandparent_inheritance_triggers`
   - SuperAdmin(Admin(User))
   - Change User.validate()
   - SuperAdmin subscription should trigger

### Cross-File Tests (Phase 2)
1. `test_cross_file_inheritance_triggers`
   - User in user.py
   - Admin(User) in admin.py
   - Change User.validate()
   - Admin subscription should trigger
