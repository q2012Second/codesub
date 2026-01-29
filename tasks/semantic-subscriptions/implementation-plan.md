# Implementation Plan: Semantic Code Subscriptions

> **Self-contained plan for implementation after context clear**

## Overview

Add semantic subscriptions to codesub that track Python code constructs (variables, constants, class fields, methods) by identity rather than line numbers. Detect changes to type annotations, default values, method signatures, and body content.

## MVP Scope

### Included
- **Module variables/constants**: `MAX_RETRIES = 5`, `TIMEOUT: int = 30`
- **Class fields**: `class User: role: str = "user"`
- **Methods**: `class User: def save(self, path: str = "tmp") -> None`

### Change Detection
| Change Type | Example | Result |
|-------------|---------|--------|
| Type annotation changed | `x: int` → `x: float` | STRUCTURAL trigger |
| Default value changed | `x = 5` → `x = 10` | CONTENT trigger |
| Method param default changed | `def f(x=1)` → `def f(x=2)` | STRUCTURAL trigger |
| Method body changed | New statement added | CONTENT trigger |
| Renamed/moved (same content) | `foo` → `bar` | PROPOSAL (no trigger) |
| Renamed + changed | `foo=1` → `bar=2` | PROPOSAL + CONTENT trigger |
| Deleted | Symbol removed | MISSING trigger |
| Formatting only | Whitespace/comments | No action (COSMETIC) |

### Deferred
- Instance attributes (`self.x = ...` in `__init__`)
- Local variables inside functions
- Nested functions
- Fuzzy matching
- Java/Go support

---

## Design Decisions

### 1. Unified Model
Extend existing `Subscription` with optional `semantic` field. Do NOT create separate model.

### 2. FQN Format
```
path/to/file.py::QualName
path/to/file.py::kind:QualName   # disambiguation if needed
```

Examples:
- `src/settings.py::MAX_RETRIES` - module constant
- `src/models.py::User.role` - class field
- `src/models.py::User.save` - method
- `src/a.py::field:Config.TIMEOUT` - explicit kind

Kinds: `variable`, `const`, `field`, `method`

### 3. Fingerprinting
Two hashes per construct:

| Hash | Contents | Detects |
|------|----------|---------|
| `interface_hash` | kind + type annotation + decorators + (for methods: params with types/defaults) | Signature/type changes |
| `body_hash` | Value expression tokens (variables/fields) or body tokens (methods), excluding comments/whitespace | Value/body changes |

### 4. Two-Stage Matching
1. **Stage 1 (Exact)**: Match by `(path, kind, qualname)`
2. **Stage 2 (Hash-based)**: If not found, search changed `.py` files:
   - Match on `(interface_hash, body_hash)` → rename only
   - Match on `body_hash` only → rename + signature change
   - Match on `interface_hash` only → rename + body change
   - Require **unique** match; otherwise mark ambiguous

### 5. Proposal + Trigger
A semantic subscription can produce BOTH:
- **Proposal**: When construct moved/renamed (update subscription target)
- **Trigger**: When content/signature changed (notify user)

---

## Data Model Changes

### File: `src/codesub/models.py`

```python
# Add new dataclass
@dataclass
class SemanticTarget:
    """Semantic identifier for a code construct."""
    language: str           # "python"
    kind: str               # "variable"|"field"|"method"
    qualname: str           # "MAX_RETRIES" | "User.role" | "User.save"
    role: str | None = None # "const" for constants, else None

    interface_hash: str = ""
    body_hash: str = ""
    fingerprint_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "kind": self.kind,
            "qualname": self.qualname,
            "role": self.role,
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
            role=data.get("role"),
            interface_hash=data.get("interface_hash", ""),
            body_hash=data.get("body_hash", ""),
            fingerprint_version=data.get("fingerprint_version", 1),
        )


# Extend Subscription - add field:
@dataclass
class Subscription:
    # ... existing fields ...
    semantic: SemanticTarget | None = None

    # Update to_dict to include:
    # if self.semantic is not None:
    #     result["semantic"] = self.semantic.to_dict()

    # Update from_dict to parse:
    # semantic = SemanticTarget.from_dict(data["semantic"]) if data.get("semantic") else None


# Extend Trigger - add fields:
@dataclass
class Trigger:
    # ... existing fields ...
    change_type: str | None = None   # "STRUCTURAL"|"CONTENT"|"MISSING"|"AMBIGUOUS"|"PARSE_ERROR"
    details: dict[str, Any] | None = None


# Extend Proposal - add fields:
@dataclass
class Proposal:
    # ... existing fields ...
    new_qualname: str | None = None
    new_kind: str | None = None
```

---

## New Files

### File: `src/codesub/semantic/__init__.py`
```python
"""Semantic code analysis for codesub."""
from .python_indexer import PythonIndexer, Construct
from .fingerprint import compute_fingerprint

__all__ = ["PythonIndexer", "Construct", "compute_fingerprint"]
```

### File: `src/codesub/semantic/python_indexer.py`

```python
"""Python construct extraction using Tree-sitter."""
from dataclasses import dataclass
import tree_sitter
import tree_sitter_python as tspython
from .fingerprint import compute_interface_hash, compute_body_hash


@dataclass(frozen=True)
class Construct:
    """A parsed code construct."""
    path: str
    kind: str           # "variable"|"field"|"method"
    qualname: str       # "MAX_RETRIES" | "User.role"
    role: str | None    # "const" for constants
    start_line: int
    end_line: int
    interface_hash: str
    body_hash: str
    has_parse_error: bool = False


class PythonIndexer:
    """Extracts constructs from Python source code."""

    def __init__(self):
        self._language = tree_sitter.Language(tspython.language())
        self._parser = tree_sitter.Parser(self._language)

    def index_file(self, source: str, path: str) -> list[Construct]:
        """Extract all constructs from source code."""
        tree = self._parser.parse(source.encode())
        has_errors = self._has_errors(tree.root_node)
        constructs = []

        # Extract module-level assignments (variables/constants)
        constructs.extend(self._extract_module_assignments(
            tree.root_node, source, path, has_errors
        ))

        # Extract classes with their fields and methods
        constructs.extend(self._extract_classes(
            tree.root_node, source, path, has_errors
        ))

        return constructs

    def find_construct(self, source: str, path: str, qualname: str,
                       kind: str | None = None) -> Construct | None:
        """Find a specific construct by qualname."""
        constructs = self.index_file(source, path)
        matches = [c for c in constructs if c.qualname == qualname]
        if kind:
            matches = [c for c in matches if c.kind == kind]
        return matches[0] if len(matches) == 1 else None

    def _has_errors(self, node: tree_sitter.Node) -> bool:
        """Check if tree contains ERROR nodes."""
        if node.type == "ERROR":
            return True
        return any(self._has_errors(child) for child in node.children)

    def _extract_module_assignments(self, root, source, path, has_errors):
        """Extract module-level variable/constant assignments."""
        constructs = []
        source_bytes = source.encode()

        for child in root.children:
            # Handle: NAME = value
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr and expr.type == "assignment":
                    construct = self._parse_assignment(
                        expr, source_bytes, path, None, has_errors
                    )
                    if construct:
                        constructs.append(construct)

            # Handle: NAME: type = value  OR  NAME: type
            elif child.type == "annotated_assignment":
                construct = self._parse_annotated_assignment(
                    child, source_bytes, path, None, has_errors
                )
                if construct:
                    constructs.append(construct)

        return constructs

    def _extract_classes(self, root, source, path, has_errors):
        """Extract classes with their fields and methods."""
        constructs = []
        source_bytes = source.encode()

        for child in root.children:
            if child.type == "class_definition":
                class_name = self._get_name(child)
                if not class_name:
                    continue

                # Get class body
                body = child.child_by_field_name("body")
                if not body:
                    continue

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

                    # Class field: x: type = value OR x: type
                    elif member.type == "annotated_assignment":
                        construct = self._parse_annotated_assignment(
                            member, source_bytes, path, class_name, has_errors
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
                                func, source_bytes, path, class_name, has_errors,
                                decorated_node=member
                            )
                            if construct:
                                constructs.append(construct)

        return constructs

    def _parse_assignment(self, node, source_bytes, path, class_name, has_errors):
        """Parse: NAME = value"""
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if not left or left.type != "identifier":
            return None

        name = self._node_text(left, source_bytes)
        qualname = f"{class_name}.{name}" if class_name else name
        kind = "field" if class_name else "variable"
        role = "const" if self._is_constant_name(name) else None

        # interface_hash: just the kind (no type annotation)
        interface_hash = compute_interface_hash(kind, annotation=None, decorators=[])

        # body_hash: the RHS value
        body_hash = compute_body_hash(right, source_bytes) if right else ""

        return Construct(
            path=path,
            kind=kind,
            qualname=qualname,
            role=role,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _parse_annotated_assignment(self, node, source_bytes, path, class_name, has_errors):
        """Parse: NAME: type = value  OR  NAME: type"""
        name_node = node.child_by_field_name("name")
        type_node = node.child_by_field_name("type")
        value_node = node.child_by_field_name("value")  # May be None

        if not name_node or name_node.type != "identifier":
            return None

        name = self._node_text(name_node, source_bytes)
        qualname = f"{class_name}.{name}" if class_name else name
        kind = "field" if class_name else "variable"
        role = "const" if self._is_constant_name(name) else None

        # interface_hash: includes type annotation
        annotation = self._node_text(type_node, source_bytes) if type_node else None
        interface_hash = compute_interface_hash(kind, annotation=annotation, decorators=[])

        # body_hash: the RHS value (or "<no-default>")
        if value_node:
            body_hash = compute_body_hash(value_node, source_bytes)
        else:
            body_hash = compute_body_hash(None, source_bytes)  # "<no-default>"

        return Construct(
            path=path,
            kind=kind,
            qualname=qualname,
            role=role,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _parse_method(self, node, source_bytes, path, class_name, has_errors,
                      decorated_node=None):
        """Parse method definition."""
        name = self._get_name(node)
        if not name:
            return None

        qualname = f"{class_name}.{name}"

        # Get decorators
        decorators = []
        if decorated_node:
            for child in decorated_node.children:
                if child.type == "decorator":
                    decorators.append(self._node_text(child, source_bytes))

        # Get parameters for interface_hash
        params_node = node.child_by_field_name("parameters")
        return_type = node.child_by_field_name("return_type")

        interface_hash = compute_interface_hash(
            "method",
            annotation=self._node_text(return_type, source_bytes) if return_type else None,
            decorators=decorators,
            params_node=params_node,
            source_bytes=source_bytes,
        )

        # Get body for body_hash
        body_node = node.child_by_field_name("body")
        body_hash = compute_body_hash(body_node, source_bytes) if body_node else ""

        use_node = decorated_node or node
        return Construct(
            path=path,
            kind="method",
            qualname=qualname,
            role=None,
            start_line=use_node.start_point[0] + 1,
            end_line=use_node.end_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _get_name(self, node) -> str | None:
        """Get name from class/function definition."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode() if name_node.text else None
        return None

    def _node_text(self, node, source_bytes) -> str:
        """Get text content of a node."""
        return source_bytes[node.start_byte:node.end_byte].decode()

    def _is_constant_name(self, name: str) -> bool:
        """Check if name follows CONSTANT_CASE convention."""
        import re
        return bool(re.match(r'^[A-Z][A-Z0-9_]*$', name))
```

### File: `src/codesub/semantic/fingerprint.py`

```python
"""Fingerprint computation for code constructs."""
import hashlib
import tree_sitter


def compute_interface_hash(
    kind: str,
    annotation: str | None,
    decorators: list[str],
    params_node: tree_sitter.Node | None = None,
    source_bytes: bytes | None = None,
) -> str:
    """
    Compute interface hash (rename-resistant).

    Includes: kind, type annotation, decorators, method parameters with types/defaults
    Excludes: construct name
    """
    components = [kind]

    # Add type annotation
    components.append(annotation or "<no-annotation>")

    # Add sorted decorators
    components.extend(sorted(decorators))

    # Add method parameters if present
    if params_node and source_bytes:
        params_str = _normalize_params(params_node, source_bytes)
        components.append(params_str)

    return _hash(components)


def compute_body_hash(node: tree_sitter.Node | None, source_bytes: bytes) -> str:
    """
    Compute body hash (content change detection).

    Includes: all tokens except comments and whitespace
    """
    if node is None:
        return _hash(["<no-default>"])

    tokens = _extract_tokens(node, source_bytes)
    return _hash(tokens)


def _normalize_params(params_node: tree_sitter.Node, source_bytes: bytes) -> str:
    """Extract normalized parameter representation including types and defaults."""
    parts = []
    for child in params_node.children:
        if child.type in ("identifier", "typed_parameter", "default_parameter",
                          "typed_default_parameter", "list_splat_pattern",
                          "dictionary_splat_pattern"):
            # Get full text including type annotations and defaults
            text = source_bytes[child.start_byte:child.end_byte].decode()
            # Normalize whitespace
            text = " ".join(text.split())
            parts.append(text)
    return ",".join(parts)


def _extract_tokens(node: tree_sitter.Node, source_bytes: bytes) -> list[str]:
    """Extract leaf tokens, excluding comments and whitespace."""
    tokens = []
    _collect_tokens(node, source_bytes, tokens)
    return tokens


def _collect_tokens(node: tree_sitter.Node, source_bytes: bytes, tokens: list[str]):
    """Recursively collect tokens."""
    # Skip comments
    if node.type == "comment":
        return

    # Leaf node - extract text
    if len(node.children) == 0:
        text = source_bytes[node.start_byte:node.end_byte].decode().strip()
        if text:  # Skip empty/whitespace-only
            tokens.append(text)
    else:
        for child in node.children:
            _collect_tokens(child, source_bytes, tokens)


def _hash(components: list[str]) -> str:
    """Hash components into 16-char hex digest."""
    content = "\x00".join(components)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

---

## Modified Files

### File: `src/codesub/utils.py`

Add target parsing:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class LineTarget:
    """Line-based subscription target."""
    path: str
    start_line: int
    end_line: int

@dataclass(frozen=True)
class SemanticTargetSpec:
    """Semantic subscription target specification."""
    path: str
    qualname: str
    kind: str | None = None  # Optional kind for disambiguation

def parse_target_spec(spec: str) -> LineTarget | SemanticTargetSpec:
    """
    Parse target specification.

    Formats:
    - "path/to/file.py:42-50" → LineTarget
    - "path/to/file.py::QualName" → SemanticTargetSpec
    - "path/to/file.py::kind:QualName" → SemanticTargetSpec with kind
    """
    if "::" in spec:
        path, rest = spec.split("::", 1)
        if not path or not rest:
            raise InvalidLocationError(spec, "expected 'path.py::QualName'")

        # Check for kind prefix: "field:User.role"
        kind = None
        qualname = rest
        if ":" in rest and not rest.startswith(":"):
            maybe_kind, maybe_qualname = rest.split(":", 1)
            if maybe_kind in ("variable", "const", "field", "method"):
                kind = maybe_kind
                qualname = maybe_qualname

        return SemanticTargetSpec(path=path, qualname=qualname, kind=kind)

    # Fall back to line-based parsing
    path, start, end = parse_location(spec)
    return LineTarget(path=path, start_line=start, end_line=end)
```

### File: `src/codesub/cli.py`

1. **Modify `cmd_add`** to handle semantic targets
2. **Add `cmd_symbols`** command

Key changes in `cmd_add`:
```python
def cmd_add(args: argparse.Namespace) -> int:
    """Add a new subscription."""
    try:
        store, repo = get_store_and_repo()
        config = store.load()
        baseline = config.repo.baseline_ref

        from .utils import parse_target_spec, LineTarget, SemanticTargetSpec
        target = parse_target_spec(args.location)

        if isinstance(target, SemanticTargetSpec):
            # Semantic subscription
            from .semantic import PythonIndexer
            indexer = PythonIndexer()

            lines = repo.show_file(baseline, target.path)
            source = "\n".join(lines)

            construct = indexer.find_construct(
                source, target.path, target.qualname, target.kind
            )
            if construct is None:
                print(f"Error: Construct '{target.qualname}' not found in {target.path}")
                print("Use 'codesub symbols' to discover valid targets.")
                return 1

            # Extract anchors from construct lines
            context_before, watched_lines, context_after = extract_anchors(
                lines, construct.start_line, construct.end_line, context=args.context
            )
            anchors = Anchor(...)

            # Create semantic target
            semantic = SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            )

            sub = Subscription.create(
                path=target.path,
                start_line=construct.start_line,
                end_line=construct.end_line,
                label=args.label,
                description=args.desc,
                anchors=anchors,
                semantic=semantic,
            )

            store.add_subscription(sub)
            print(f"Added semantic subscription: {sub.id[:8]}")
            print(f"  Target: {construct.kind} {construct.qualname}")
            print(f"  Location: {target.path}:{construct.start_line}-{construct.end_line}")

        else:
            # Line-based subscription (existing logic)
            # ... keep existing code ...

        return 0
    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

Add `cmd_symbols`:
```python
def cmd_symbols(args: argparse.Namespace) -> int:
    """List discoverable code constructs in a file."""
    try:
        store, repo = get_store_and_repo()
        config = store.load()

        ref = args.ref or config.repo.baseline_ref
        lines = repo.show_file(ref, args.path)
        source = "\n".join(lines)

        from .semantic import PythonIndexer
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, args.path)

        # Filter by kind if specified
        if args.kind:
            constructs = [c for c in constructs if c.kind == args.kind]

        # Filter by grep pattern if specified
        if args.grep:
            constructs = [c for c in constructs if args.grep in c.qualname]

        if args.json:
            import json
            data = [{"path": c.path, "kind": c.kind, "qualname": c.qualname,
                     "start_line": c.start_line, "end_line": c.end_line,
                     "role": c.role} for c in constructs]
            print(json.dumps(data, indent=2))
        else:
            for c in constructs:
                fqn = f"{c.path}::{c.qualname}"
                role_str = f" ({c.role})" if c.role else ""
                print(f"{fqn:<50} {c.kind:<8}{role_str} ({c.start_line}-{c.end_line})")

        return 0
    except CodesubError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

Add to `create_parser`:
```python
# symbols
symbols_parser = subparsers.add_parser("symbols", help="List code constructs in a file")
symbols_parser.add_argument("path", help="File path to analyze")
symbols_parser.add_argument("--ref", help="Git ref (default: baseline)")
symbols_parser.add_argument("--kind", choices=["variable", "field", "method"],
                           help="Filter by kind")
symbols_parser.add_argument("--grep", help="Filter by name pattern")
symbols_parser.add_argument("--json", action="store_true", help="Output as JSON")
```

### File: `src/codesub/detector.py`

Add semantic detection branch in `scan()`:

```python
def scan(self, subscriptions, base_ref, target_ref=None):
    # ... existing setup ...

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

        # Existing line-based logic
        # ...


def _check_semantic(self, sub, base_ref, target_ref, rename_map, status_map):
    """Check semantic subscription for changes."""
    from .semantic import PythonIndexer
    indexer = PythonIndexer()

    trigger = None
    proposal = None

    # Resolve file rename
    old_path = sub.path
    new_path = rename_map.get(old_path, old_path)

    # Check if file deleted
    if status_map.get(old_path) == "D":
        return Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=old_path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=["file_deleted"],
            matching_hunks=[],
            change_type="MISSING",
        ), None

    # Get old and new file contents
    old_source = "\n".join(self.repo.show_file(base_ref, old_path))
    try:
        if target_ref:
            new_source = "\n".join(self.repo.show_file(target_ref, new_path))
        else:
            # Working directory
            with open(self.repo.root / new_path) as f:
                new_source = f.read()
    except Exception:
        return Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=old_path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=["file_not_found"],
            matching_hunks=[],
            change_type="MISSING",
        ), None

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
        elif (new_construct.start_line != sub.start_line or
              new_construct.end_line != sub.end_line):
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
    return Trigger(
        subscription_id=sub.id,
        subscription=sub,
        path=old_path,
        start_line=sub.start_line,
        end_line=sub.end_line,
        reasons=["semantic_target_missing"],
        matching_hunks=[],
        change_type="MISSING",
    ), None


def _classify_semantic_change(self, sub, old_construct, new_construct):
    """Classify change type between old and new construct."""
    if old_construct is None:
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


def _find_by_hash(self, semantic, constructs):
    """Find construct by hash matching."""
    # Try exact match (both hashes)
    matches = [c for c in constructs
               if c.interface_hash == semantic.interface_hash
               and c.body_hash == semantic.body_hash
               and c.kind == semantic.kind]
    if len(matches) == 1:
        return matches[0]

    # Try body-only match (renamed + signature changed)
    matches = [c for c in constructs
               if c.body_hash == semantic.body_hash
               and c.kind == semantic.kind]
    if len(matches) == 1:
        return matches[0]

    # Try interface-only match (renamed + body changed)
    matches = [c for c in constructs
               if c.interface_hash == semantic.interface_hash
               and c.kind == semantic.kind]
    if len(matches) == 1:
        return matches[0]

    return None
```

---

## Dependencies

Add to `pyproject.toml`:
```toml
[tool.poetry.dependencies]
tree-sitter = ">=0.21.0"
tree-sitter-python = ">=0.21.0"
```

---

## Testing Strategy

### Unit Tests

1. **Target parsing** (`test_utils.py`)
   - `"a.py:1-2"` → LineTarget
   - `"a.py::Foo.bar"` → SemanticTargetSpec
   - `"a.py::field:Foo.bar"` → SemanticTargetSpec with kind

2. **Python indexer** (`test_python_indexer.py`)
   - Extract module constants: `MAX = 5`
   - Extract annotated variables: `x: int = 5`
   - Extract class fields: `class C: x = 1`
   - Extract methods: `class C: def m(self): pass`
   - Verify qualnames, kinds, line ranges

3. **Fingerprinting** (`test_fingerprint.py`)
   - Formatting-only change → same hashes
   - Comment-only change → same hashes
   - Type annotation change → different interface_hash
   - Value change → different body_hash
   - Param default change → different interface_hash

4. **Semantic detector** (`test_semantic_detector.py`)
   - STRUCTURAL trigger when interface_hash differs
   - CONTENT trigger when body_hash differs
   - PROPOSAL when renamed (same hashes)
   - PROPOSAL + TRIGGER when renamed AND changed
   - MISSING when deleted

### Integration Tests

- Create git repo with semantic subscription
- Make commit that renames method → expect proposal
- Make commit that changes default value → expect CONTENT trigger
- Apply proposal → verify subscription updated

---

## Edge Cases

| Case | Handling |
|------|----------|
| File deleted | MISSING trigger with `file_deleted` reason |
| Construct deleted | MISSING trigger with `semantic_target_missing` |
| Parse errors | PARSE_ERROR trigger, no proposals |
| Multiple same-hash matches | AMBIGUOUS trigger, no proposal |
| No annotation | interface_hash uses `<no-annotation>` |
| No default value | body_hash uses `<no-default>` |
| Duplicate assignments | Use last occurrence, warn at subscribe time |

---

## Implementation Order

1. **Dependencies**: Add tree-sitter to pyproject.toml
2. **Models**: Add SemanticTarget, extend Subscription/Trigger/Proposal
3. **Semantic package**: Create indexer and fingerprint modules
4. **Utils**: Add parse_target_spec
5. **CLI**: Update cmd_add, add cmd_symbols
6. **Detector**: Add semantic detection branch
7. **Tests**: Unit tests for each module
8. **API**: Update endpoints (optional, can defer)
