# Change Tracking Improvements

Functional improvements to codesub's core change tracking capabilities.

---

## High-Impact Improvements

### 1. Cross-file Construct Movement Detection

Currently, when a construct is moved to a different file (not just renamed), the hash-based search only looks in the same/renamed file. The system could search across the entire codebase to find relocated constructs.

```
# Current: User.validate moved from auth.py to validators.py → MISSING
# Proposed: detect it moved → Proposal with new_path=validators.py
```

**Implementation notes:**
- On MISSING, optionally search all files of same language for matching hash
- Add `search_scope: file | project` option to control behavior
- Performance consideration: index all constructs upfront or search lazily

### 2. Usage/Call-Site Tracking

Track where a subscribed construct is *used*, not just the construct itself. When you subscribe to `User.validate()`, optionally detect when code that *calls* that method changes.

```yaml
subscription:
  target: auth.py::User.validate
  track_usages: true  # Also trigger when call sites change
```

**Implementation notes:**
- Use Tree-sitter queries to find call expressions matching construct name
- Store call site locations as derived subscriptions
- Change types: `CALLER_ADDED`, `CALLER_REMOVED`, `CALLER_MODIFIED`

### 3. Dependency Tracking (Imports)

Track when imports used by a subscribed construct change. If `User.validate()` imports `hashlib` and `hashlib` is replaced with `bcrypt`, that affects behavior but currently goes undetected.

**Implementation notes:**
- Parse imports at file level
- For each subscribed construct, identify which imports it uses (via name references in body)
- Trigger when those specific imports change

### 4. Inheritance-Aware Change Detection

If you track a method that overrides a parent class method, changes to the parent's signature should trigger. Currently no inheritance awareness.

```python
class BaseValidator:
    def validate(self, data): ...  # ← change here

class User(BaseValidator):
    def validate(self, data): ...  # ← subscribed here, but parent change missed
```

**Implementation notes:**
- Parse class hierarchy (extends/implements)
- For method subscriptions, identify if method overrides parent
- Check parent method for interface changes
- New reason: `parent_interface_changed`

---

## Medium-Impact Improvements

### 5. Anchor-Based Fuzzy Recovery

The `Anchor` model exists (context lines before/after) but isn't used for recovery. When a subscription can't be matched exactly after major refactoring, use fuzzy matching on anchors to find the likely new location.

**Implementation notes:**
- On construct MISSING, extract content from stored anchors
- Search file for similar content using difflib or edit distance
- Return low-confidence proposal if match found
- Add `confidence: low | medium | high` gradations

### 6. Pattern-Based Subscriptions

Subscribe to patterns rather than specific constructs:

```bash
codesub add "api/**::*Controller.*"  # All methods in Controller classes
codesub add "models.py::*.save"      # All save methods in any class
```

**Implementation notes:**
- New subscription type: `pattern`
- Expand patterns to concrete subscriptions on scan
- Track pattern alongside expanded targets
- Re-expand on each scan to catch new matches

### 7. Aggregate/Container Tracking

Track a whole class or module, triggering when *any* member changes:

```bash
codesub add auth.py::User --include-members  # Trigger if any User.* changes
```

**Implementation notes:**
- Flag on subscription: `include_members: bool`
- On scan, index all child constructs
- Aggregate change detection across members
- Report which specific members changed in trigger details

### 8. More Granular Change Classification

Current: `STRUCTURAL`, `CONTENT`, `MISSING`, `AMBIGUOUS`

Add:
- `DEPRECATED` - construct marked with deprecation decorator/annotation
- `VISIBILITY` - access modifier changed (public→private)
- `ASYNC` - sync/async status changed
- `THROWS` - exception specification changed (Java)

**Implementation notes:**
- Extract decorators/annotations into semantic metadata
- Compare decorator sets between old and new
- Add specific change reasons for each classification

---

## Lower-Impact (But Useful)

### 9. Import Statement as First-Class Constructs

Track specific imports:

```bash
codesub add config.py::import:requests  # Track "import requests" or "from requests import X"
```

**Implementation notes:**
- New construct kind: `import`
- Index import statements with Tree-sitter
- Qualname format: `import:module` or `import:module.symbol`

### 10. Docstring/Comment Tracking (Optional)

Currently excluded from `body_hash`. Add optional tracking for documentation changes:

```yaml
subscription:
  target: api.py::create_user
  track_docstrings: true
```

**Implementation notes:**
- Separate `doc_hash` computed from docstring/javadoc nodes
- New change type: `DOCUMENTATION`
- Off by default to maintain current behavior

### 11. Transitive Call Graph Analysis

Build a call graph. If function A calls function B (subscribed), and A changes, optionally surface that A could affect B's callers' behavior.

**Implementation notes:**
- Build reverse call graph (who calls what)
- For subscribed construct, find all callers
- Option to trigger on caller changes with configurable depth
- Performance: incremental call graph updates

### 12. Stale Subscription Detection

Detect when cumulative line shifts have moved a subscription so far from its original context that it may no longer track what was intended. Compare current anchor content to original.

**Implementation notes:**
- Store original anchor hash on subscription creation
- On scan, compare current content at subscription lines to original anchor
- Warn if similarity drops below threshold
- New status: `possibly_stale`

---

## Language Expansion

### 13. TypeScript/JavaScript Indexer

High value given ecosystem prevalence. Would cover:
- Functions (regular, arrow, async)
- Classes, interfaces, type aliases
- React components (functional and class-based)
- ES6 exports (named, default)
- Object methods and properties

**Tree-sitter grammar:** `tree-sitter-typescript`, `tree-sitter-javascript`

### 14. Go Indexer

Would cover:
- Functions
- Methods (with receiver types in qualname)
- Structs and interfaces
- Constants and variables
- Type definitions

**Tree-sitter grammar:** `tree-sitter-go`

---

## Priority Matrix

| Improvement | Impact | Complexity | Priority |
|-------------|--------|------------|----------|
| Cross-file movement | High | Medium | 1 |
| TypeScript indexer | High | Medium | 2 |
| Inheritance-aware | High | Medium | 3 |
| Pattern subscriptions | Medium | Medium | 4 |
| Usage tracking | High | High | 5 |
| Aggregate tracking | Medium | Low | 6 |
| Granular classification | Medium | Low | 7 |
| Anchor fuzzy recovery | Medium | Medium | 8 |
| Go indexer | Medium | Medium | 9 |
| Import tracking | Low | Low | 10 |
| Dependency tracking | Medium | High | 11 |
| Docstring tracking | Low | Low | 12 |
| Stale detection | Low | Medium | 13 |
| Call graph analysis | Medium | High | 14 |
