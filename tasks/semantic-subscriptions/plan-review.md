# Plan Review: Semantic Code Subscriptions

## Summary

This is a well-thought-out plan for adding semantic code subscriptions to codesub. The core design decisions are sound, and the plan demonstrates good understanding of the existing architecture. However, there are several areas that need clarification, potential simplifications, and risk mitigation before implementation.

---

## Issues Found

### Critical Issues

#### 1. Missing File Content Access Strategy
- **Severity:** Critical
- **Description:** The plan mentions "snapshot-based comparison" where both old and new versions are parsed, but the existing `GitRepo` class only provides `show_file(ref, path)` which returns file lines. For Tree-sitter parsing, you need the raw file content as bytes or a string. More importantly, the plan does not address how to handle the case where a file exists only in the new version (new files) or only in the old version (deleted files). The current detector relies on git diff output which handles this naturally.
- **Suggested Fix:** Add a method to `GitRepo` like `get_file_content(ref: str, path: str) -> str` that returns raw content suitable for Tree-sitter. Explicitly document in the plan how new/deleted files are handled by the semantic detector.

#### 2. Unclear Construct Matching with Subscriptions
- **Severity:** Critical
- **Description:** The plan describes `SemanticTarget` with `fqn` and `construct_kind`, but does not clearly define how a user specifies what to subscribe to. Currently users use `path:start-end` format. How does a user create a semantic subscription? The plan mentions `add-semantic` CLI command but does not specify the input format. Is it `path:MyClass.my_method`? Is it interactive where the user sees parsed constructs? This is a fundamental UX question that affects the entire implementation.
- **Suggested Fix:** Define the exact CLI interface for `add-semantic`. Options include:
  - `codesub add-semantic path/to/file.py:MyClass.method_name`
  - `codesub add-semantic --fqn "module.Class.method"`
  - Interactive mode: `codesub parse path/to/file.py` shows constructs, then user picks one

#### 3. Body Hash Normalization Undefined
- **Severity:** Critical
- **Description:** The plan mentions `body_hash_normalized` with "token normalization, alpha-renaming" but these are complex concepts that need precise definition. What exactly gets normalized? Just identifiers? What about string literals, numbers, comments? Alpha-renaming of local variables is language-specific and complex (closures, nested scopes). This could easily become a rabbit hole.
- **Suggested Fix:** Define explicit normalization rules for Python as MVP:
  - Remove comments and docstrings
  - Normalize whitespace
  - (Optional for v1) Alpha-rename local variables

  Consider deferring alpha-renaming to a later version and starting with simpler hash strategies that still provide value.

---

### Major Issues

#### 4. Fingerprint Stability Across Tree-sitter Versions
- **Severity:** Major
- **Description:** Tree-sitter parse trees can change between versions. If node types or tree structure changes, all fingerprints could become invalid. The plan does not address versioning of fingerprints or migration strategy.
- **Suggested Fix:** Store tree-sitter grammar version with fingerprints in the subscription. Add migration logic to recompute fingerprints when grammar versions change. Alternatively, make fingerprints less dependent on tree structure by hashing content rather than AST structure.

#### 5. Multi-Stage Matching Complexity
- **Severity:** Major
- **Description:** The plan proposes "exact -> rename-resistant -> move detection -> fuzzy" matching stages. This is 4 distinct algorithms, each with potential edge cases. The plan does not define what "fuzzy" matching means or when to stop matching. This could lead to false positives (wrong matches) which are worse than false negatives (no match found).
- **Suggested Fix:** Start with 2 stages for MVP:
  1. Exact match (same FQN, same file)
  2. Rename/move detection (same interface_hash + body_hash_normalized)

  Defer fuzzy matching to a later version. Be conservative - it's better to trigger a review than to silently track the wrong construct.

#### 6. Dual Model Complexity
- **Severity:** Major
- **Description:** Having both `Subscription` (line-based) and `SemanticSubscription` as separate models stored in the same config creates complexity. The plan mentions `UnifiedDetector` but the config schema shows them as parallel lists. This means every CRUD operation, every API endpoint, every CLI command needs to handle both types.
- **Suggested Fix:** Consider a single `Subscription` model with an optional `semantic_target` field. This reduces duplication:
```python
@dataclass
class Subscription:
    id: str
    path: str
    start_line: int
    end_line: int
    semantic_target: SemanticTarget | None = None  # If set, use semantic tracking
    ...
```
Line numbers still exist (computed from construct location) but semantic_target drives the matching logic.

#### 7. No Handling for Partial Parses / Syntax Errors
- **Severity:** Major
- **Description:** Real codebases often have files with syntax errors during development. Tree-sitter handles this gracefully (error recovery), but the plan does not address how semantic subscriptions behave when the target file cannot be fully parsed or when the subscribed construct contains syntax errors.
- **Suggested Fix:** Define explicit behavior:
  - If construct cannot be found due to parse errors: treat as "triggered" (needs human review)
  - Store parse error state in ScanResult for debugging
  - Add `parse_errors` field to Trigger/Proposal

---

### Minor Issues

#### 8. Language Plugin Design Not Detailed
- **Severity:** Minor
- **Description:** The plan mentions "Language plugins via abstract base" but does not show the interface. While Python-only for MVP is fine, the abstract base should be designed with future languages in mind.
- **Suggested Fix:** Sketch the `LanguageParser` interface in the plan:
```python
class LanguageParser(ABC):
    @abstractmethod
    def supported_extensions(self) -> list[str]: ...
    @abstractmethod
    def parse(self, content: str) -> tree_sitter.Tree: ...
    @abstractmethod
    def extract_constructs(self, tree: tree_sitter.Tree, file_path: str) -> list[Construct]: ...
```

#### 9. FQN Format Not Specified
- **Severity:** Minor
- **Description:** FQN (Fully Qualified Name) format varies by language. The plan does not specify what format codesub will use. Python: `module.Class.method`? Include file path? What about nested classes?
- **Suggested Fix:** Define FQN format explicitly:
  - Python: `file/path.py::ClassName.method_name` or `file/path.py::top_level_function`
  - Nested: `file/path.py::Outer.Inner.method`

#### 10. Missing `doc_hash` Purpose
- **Severity:** Minor
- **Description:** The plan lists `doc_hash` in fingerprints but never explains its purpose. Is it for detecting documentation-only changes? How is it used in matching?
- **Suggested Fix:** Either remove `doc_hash` if not needed, or explain its role in change classification (e.g., "cosmetic" changes that only affect docstrings).

#### 11. ChangeType Enum Values Not Listed
- **Severity:** Minor
- **Description:** The plan mentions `ChangeType enum` for change classification but does not list the values or how they map to different scenarios.
- **Suggested Fix:** Define explicitly:
```python
class ChangeType(Enum):
    STRUCTURAL = "structural"    # Signature changed (interface_hash differs)
    CONTENT = "content"          # Body changed (body_hash differs)
    LOCATION = "location"        # Moved/renamed but same content
    COSMETIC = "cosmetic"        # Only whitespace/comments/docs changed
```

---

## Strengths

1. **Good foundation choices:** Tree-sitter is the right choice for multi-language parsing with error tolerance
2. **Backward compatibility focus:** Keeping line-based subscriptions working is important for adoption
3. **Snapshot-based comparison:** More reliable than trying to interpret diffs semantically
4. **Unified output format:** Using the same Trigger/Proposal output enables existing downstream tooling
5. **Clear separation of concerns:** Parser, extractor, matcher, detector as separate modules enables testing
6. **Testing strategy mentioned:** Unit tests per module plus integration tests is appropriate

---

## Verdict

**NEEDS REVISION**

The plan has a solid foundation but requires the following changes before implementation:

1. **Define the user interface for creating semantic subscriptions** - This is blocking; we cannot implement without knowing how users will interact with the feature
2. **Simplify body normalization** - Defer alpha-renaming, define simpler rules for v1
3. **Reduce matching stages to 2** - Exact match and rename-resistant only for MVP
4. **Add file content access method to GitRepo** - Prerequisite for parsing
5. **Consider unified Subscription model** - Reduces implementation complexity significantly
6. **Define explicit behavior for parse errors** - Important for real-world usage

---

## Recommended Revisions for MVP

### Simplified Scope

| Original | Recommended MVP |
|----------|-----------------|
| 4-stage matching | 2-stage: exact + rename/move |
| Alpha-renamed body hash | Simple body hash (no alpha-renaming) |
| Separate SemanticSubscription model | Extend existing Subscription with optional semantic_target |
| Fuzzy matching | Defer to v2 |
| doc_hash | Remove for MVP |

### Key Questions to Resolve

1. How does a user specify what construct to subscribe to?
2. What happens when a construct can't be found at scan time?
3. How are fingerprints recomputed when tree-sitter versions change?
