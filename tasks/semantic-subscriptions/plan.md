# Implementation Plan: Semantic Code Subscriptions

## Overview
Implement semantic code subscriptions using Tree-sitter parsing and fingerprinting-based tracking. This enables tracking code constructs (functions, classes, methods) by identity rather than just line numbers, with sophisticated change classification that distinguishes structural changes from cosmetic ones.

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Tree-sitter for parsing | Industry-standard, multi-language support, error-tolerant, fast incremental parsing |
| Snapshot-based comparison | More reliable than diff-based; parse both old and new versions to detect all changes |
| Multi-hash fingerprinting | Enables rename detection (interface_hash), content change detection (body_hash), and refactoring resistance (body_hash_normalized) |
| Separate SemanticSubscription model | Maintains backward compatibility; line-based and semantic subscriptions coexist |
| Unified ScanResult | Both subscription types produce the same Trigger/Proposal output for consistent downstream handling |
| Language plugins via abstract base | Clean extension point for Java/Go without modifying core logic |

**User Requirements:**
- Start with Python support, design for Java/Go extension
- Multi-hash fingerprinting with specific hash types
- Multi-stage matching pipeline (exact -> rename-resistant -> move detection -> fuzzy)
- Change classification: structural/content/location/cosmetic
- Backward compatible with existing line-based subscriptions

**Alternative Approaches Considered:**
- **Diff-based detection only**: Rejected because it cannot detect cross-file moves or reliably classify change types
- **Single fingerprint hash**: Rejected because different hash types serve different purposes (rename vs. content vs. refactoring detection)
- **Replace line-based subscriptions entirely**: Rejected to maintain backward compatibility and because line-based is still useful for non-code files

## Prerequisites
- Install Tree-sitter: `poetry add tree-sitter tree-sitter-python`
- Future: `tree-sitter-java tree-sitter-go` for additional languages

---

## Implementation Steps

### Step 1: Add New Data Models
**Files:** `src/codesub/models.py`

**Changes:**
- Add `ConstructKind` enum (FUNCTION, CLASS, METHOD, VARIABLE, MODULE)
- Add `Fingerprint` dataclass with interface_hash, body_hash, body_hash_normalized, doc_hash
- Add `Construct` dataclass representing a parsed code construct
- Add `SemanticTarget` dataclass for semantic subscription target
- Add `SemanticSubscription` dataclass (parallel to line-based Subscription)
- Add `ChangeType` enum (STRUCTURAL, CONTENT, LOCATION, COSMETIC, NONE)
- Add `SemanticTrigger` and `SemanticProposal` models
- Extend `Config` to include semantic_subscriptions list

**Code:**
```python
from enum import Enum

class ConstructKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"

@dataclass
class Fingerprint:
    """Multi-hash fingerprint for a code construct."""
    interface_hash: str  # kind + params + decorators (excludes name)
    body_hash: str       # normalized tokens excluding whitespace/comments
    body_hash_normalized: str  # alpha-renamed local variables
    doc_hash: str | None = None  # docstring/comments hash

@dataclass
class Construct:
    """A parsed code construct from the AST."""
    kind: ConstructKind
    name: str
    fqn: str  # Fully qualified name (e.g., "module.Class.method")
    path: str  # File path
    start_line: int
    end_line: int
    parent_fqn: str | None  # Parent construct FQN
    fingerprint: Fingerprint
    signature: str | None  # Human-readable signature for display
    decorators: list[str] = field(default_factory=list)

@dataclass
class SemanticTarget:
    """Target for a semantic subscription."""
    path: str
    fqn: str
    kind: ConstructKind
    fingerprint: Fingerprint  # Fingerprint at subscription time

@dataclass
class SemanticSubscription:
    """A subscription to a semantic code construct."""
    id: str
    target: SemanticTarget
    label: str | None = None
    description: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

class ChangeType(str, Enum):
    STRUCTURAL = "structural"  # Signature changed
    CONTENT = "content"        # Body changed
    LOCATION = "location"      # Moved/renamed
    COSMETIC = "cosmetic"      # Formatting/comments only
    DELETED = "deleted"        # Construct removed
    NONE = "none"              # No change
```

---

### Step 2: Create Parser Abstraction
**Files:** `src/codesub/parser.py` (new file)

**Changes:**
- Create `LanguageParser` abstract base class
- Create `PythonParser` implementation
- Define common interface for construct extraction

**Code:**
```python
"""Tree-sitter parsing abstraction for codesub."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

import tree_sitter
import tree_sitter_python as tspython

from .models import Construct, ConstructKind


class LanguageParser(ABC):
    """Abstract base class for language-specific parsers."""

    @property
    @abstractmethod
    def language_name(self) -> str:
        """Return the language name (e.g., 'python', 'java')."""
        pass

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """Return supported file extensions (e.g., ['.py'])."""
        pass

    @abstractmethod
    def parse(self, source: str, path: str) -> list[Construct]:
        """Parse source code and extract all constructs."""
        pass

    @abstractmethod
    def extract_construct(self, source: str, path: str, fqn: str) -> Construct | None:
        """Extract a specific construct by FQN."""
        pass


class PythonParser(LanguageParser):
    """Python parser using tree-sitter."""

    def __init__(self):
        self._language = tree_sitter.Language(tspython.language())
        self._parser = tree_sitter.Parser(self._language)

    @property
    def language_name(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> list[str]:
        return [".py"]

    def parse(self, source: str, path: str) -> list[Construct]:
        tree = self._parser.parse(source.encode())
        return self._extract_constructs(tree.root_node, source, path, parent_fqn=None)

    # ... implementation details
```

---

### Step 3: Create Fingerprint Module
**Files:** `src/codesub/fingerprint.py` (new file)

**Changes:**
- Implement `compute_fingerprint()` function
- Implement hash computation for each fingerprint type
- Implement token normalization for body_hash
- Implement alpha-renaming for body_hash_normalized

**Code:**
```python
"""Fingerprint computation for code constructs."""

import hashlib
import re
from typing import Sequence

import tree_sitter

from .models import Fingerprint, ConstructKind


def compute_fingerprint(
    node: tree_sitter.Node,
    source: bytes,
    kind: ConstructKind,
    decorators: list[str],
) -> Fingerprint:
    """Compute multi-hash fingerprint for a code construct."""
    interface_hash = _compute_interface_hash(node, source, kind, decorators)
    body_hash = _compute_body_hash(node, source)
    body_hash_normalized = _compute_body_hash_normalized(node, source)
    doc_hash = _compute_doc_hash(node, source)

    return Fingerprint(
        interface_hash=interface_hash,
        body_hash=body_hash,
        body_hash_normalized=body_hash_normalized,
        doc_hash=doc_hash,
    )


def _compute_interface_hash(
    node: tree_sitter.Node,
    source: bytes,
    kind: ConstructKind,
    decorators: list[str],
) -> str:
    """Compute interface hash: kind + params + decorators (excludes name)."""
    components = [kind.value]
    components.extend(sorted(decorators))

    # Extract parameter types/defaults for functions/methods
    params = _extract_parameters(node, source)
    components.extend(params)

    return _hash_components(components)


def _compute_body_hash(node: tree_sitter.Node, source: bytes) -> str:
    """Compute body hash: normalized tokens excluding whitespace/comments."""
    tokens = _tokenize_body(node, source, exclude_comments=True)
    normalized = _normalize_tokens(tokens)
    return _hash_components(normalized)


def _compute_body_hash_normalized(node: tree_sitter.Node, source: bytes) -> str:
    """Compute normalized body hash with alpha-renamed local variables."""
    tokens = _tokenize_body(node, source, exclude_comments=True)
    normalized = _normalize_tokens(tokens)
    alpha_renamed = _alpha_rename_locals(normalized)
    return _hash_components(alpha_renamed)


def _hash_components(components: Sequence[str]) -> str:
    """Hash a sequence of components into a hex digest."""
    content = "\x00".join(components)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

---

### Step 4: Create Construct Extractor
**Files:** `src/codesub/extractor.py` (new file)

**Changes:**
- Implement `ConstructExtractor` class that uses parser and fingerprint modules
- Handle nested constructs (classes containing methods)
- Build FQN for each construct
- Extract decorators and signatures

**Code:**
```python
"""Extract constructs from parsed code."""

from .parser import LanguageParser, PythonParser
from .fingerprint import compute_fingerprint
from .models import Construct, ConstructKind, Fingerprint


class ConstructExtractor:
    """Extracts constructs from source files using language-specific parsers."""

    def __init__(self):
        self._parsers: dict[str, LanguageParser] = {}
        self._register_parser(PythonParser())

    def _register_parser(self, parser: LanguageParser) -> None:
        for ext in parser.file_extensions:
            self._parsers[ext] = parser

    def supports_file(self, path: str) -> bool:
        """Check if file type is supported."""
        ext = self._get_extension(path)
        return ext in self._parsers

    def extract_all(self, source: str, path: str) -> list[Construct]:
        """Extract all constructs from a source file."""
        parser = self._get_parser(path)
        if parser is None:
            return []
        return parser.parse(source, path)

    def extract_by_fqn(self, source: str, path: str, fqn: str) -> Construct | None:
        """Extract a specific construct by FQN."""
        parser = self._get_parser(path)
        if parser is None:
            return None
        return parser.extract_construct(source, path, fqn)

    def build_construct_index(
        self, constructs: list[Construct]
    ) -> dict[str, Construct]:
        """Build an index from FQN to Construct."""
        return {c.fqn: c for c in constructs}
```

---

### Step 5: Create Matcher Module
**Files:** `src/codesub/matcher.py` (new file)

**Changes:**
- Implement `ConstructMatcher` class with multi-stage matching pipeline
- Stage 1: Exact match (FQN + full fingerprint)
- Stage 2: Rename-resistant match (parent + interface_hash + body_hash)
- Stage 3: Move detection (search across files by body_hash)
- Stage 4: Fuzzy match using structural similarity (last resort)

**Code:**
```python
"""Multi-stage construct matching for change detection."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .models import Construct, Fingerprint, ChangeType


class MatchConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class MatchResult:
    """Result of matching a construct between versions."""
    old_construct: Construct
    new_construct: Construct | None
    confidence: MatchConfidence
    change_type: ChangeType
    reasons: list[str]


class ConstructMatcher:
    """Multi-stage matching pipeline for constructs."""

    def match(
        self,
        old_construct: Construct,
        new_constructs_by_fqn: dict[str, Construct],
        new_constructs_by_path: dict[str, list[Construct]],
        all_new_constructs: list[Construct],
    ) -> MatchResult:
        """
        Find the matching construct in the new version using multi-stage pipeline.
        """
        # Stage 1: Exact match by FQN
        if old_construct.fqn in new_constructs_by_fqn:
            new = new_constructs_by_fqn[old_construct.fqn]
            change_type = self._classify_change(old_construct, new)
            return MatchResult(
                old_construct=old_construct,
                new_construct=new,
                confidence=MatchConfidence.EXACT,
                change_type=change_type,
                reasons=["exact_fqn_match"],
            )

        # Stage 2: Rename-resistant match (same parent + interface + body)
        result = self._match_by_interface_and_body(old_construct, new_constructs_by_path)
        if result:
            return result

        # Stage 3: Move detection (search all files by body_hash)
        result = self._match_by_body_hash(old_construct, all_new_constructs)
        if result:
            return result

        # Stage 4: Fuzzy structural similarity
        result = self._match_by_similarity(old_construct, all_new_constructs)
        if result:
            return result

        # No match found - construct was deleted
        return MatchResult(
            old_construct=old_construct,
            new_construct=None,
            confidence=MatchConfidence.EXACT,
            change_type=ChangeType.DELETED,
            reasons=["construct_deleted"],
        )

    def _classify_change(self, old: Construct, new: Construct) -> ChangeType:
        """Classify the type of change between two constructs."""
        fp_old = old.fingerprint
        fp_new = new.fingerprint

        # Check interface (structural) change
        if fp_old.interface_hash != fp_new.interface_hash:
            return ChangeType.STRUCTURAL

        # Check content change
        if fp_old.body_hash != fp_new.body_hash:
            # Check if it's just refactoring (local variable renames)
            if fp_old.body_hash_normalized != fp_new.body_hash_normalized:
                return ChangeType.CONTENT
            # body_hash_normalized matches - it's just local var renames
            return ChangeType.COSMETIC

        # Check location change
        if old.path != new.path or old.fqn != new.fqn:
            return ChangeType.LOCATION

        # Check cosmetic change (doc/formatting only)
        if fp_old.doc_hash != fp_new.doc_hash:
            return ChangeType.COSMETIC

        return ChangeType.NONE
```

---

### Step 6: Create Semantic Detector
**Files:** `src/codesub/semantic_detector.py` (new file)

**Changes:**
- Implement `SemanticDetector` class that uses extractor and matcher
- Parse both old and new versions of files
- For each subscription, find and match constructs
- Generate triggers for structural/content changes
- Generate proposals for location changes
- Handle deleted constructs

**Code:**
```python
"""Semantic change detection for codesub."""

from .extractor import ConstructExtractor
from .git_repo import GitRepo
from .matcher import ConstructMatcher, MatchConfidence
from .models import (
    SemanticSubscription, Construct, ChangeType,
    Trigger, Proposal, ScanResult
)


class SemanticDetector:
    """Detects semantic changes to subscribed code constructs."""

    def __init__(self, repo: GitRepo):
        self.repo = repo
        self.extractor = ConstructExtractor()
        self.matcher = ConstructMatcher()

    def scan(
        self,
        subscriptions: list[SemanticSubscription],
        base_ref: str,
        target_ref: str | None = None,
    ) -> ScanResult:
        """Scan for semantic changes between two refs."""
        active_subs = [s for s in subscriptions if s.active]
        display_target = target_ref or "WORKING"

        if not active_subs:
            return ScanResult(
                base_ref=base_ref,
                target_ref=display_target,
                triggers=[],
                proposals=[],
                unchanged=[],
            )

        # Get unique file paths from subscriptions
        paths = set(s.target.path for s in active_subs)

        # Parse constructs in both versions
        old_constructs = self._parse_version(base_ref, paths)
        new_constructs = self._parse_version(target_ref, paths)

        # Build indices
        new_by_fqn = {c.fqn: c for c in new_constructs}
        new_by_path = self._group_by_path(new_constructs)

        triggers = []
        proposals = []
        unchanged = []

        for sub in active_subs:
            # Find the old construct
            old_construct = self._find_construct(
                old_constructs, sub.target.path, sub.target.fqn
            )

            if old_construct is None:
                continue

            # Match to new version
            result = self.matcher.match(
                old_construct, new_by_fqn, new_by_path, new_constructs
            )

            # Generate trigger or proposal based on change type
            if result.change_type in (ChangeType.STRUCTURAL, ChangeType.CONTENT, ChangeType.DELETED):
                triggers.append(self._create_trigger(sub, old_construct, result))
            elif result.change_type == ChangeType.LOCATION:
                proposals.append(self._create_proposal(sub, old_construct, result))
            else:
                unchanged.append(sub)

        return ScanResult(
            base_ref=base_ref,
            target_ref=display_target,
            triggers=triggers,
            proposals=proposals,
            unchanged=unchanged,
        )
```

---

### Step 7: Integrate with Existing Detector
**Files:** `src/codesub/detector.py`

**Changes:**
- Add `UnifiedDetector` class that combines line-based and semantic detection
- Modify `scan()` to handle both subscription types
- Keep existing `Detector` for backward compatibility

**Code:**
```python
# Add to existing detector.py

from .semantic_detector import SemanticDetector
from .models import SemanticSubscription


class UnifiedDetector:
    """Unified detector that handles both line-based and semantic subscriptions."""

    def __init__(self, repo: GitRepo):
        self.line_detector = Detector(repo)
        self.semantic_detector = SemanticDetector(repo)

    def scan(
        self,
        line_subscriptions: list[Subscription],
        semantic_subscriptions: list[SemanticSubscription],
        base_ref: str,
        target_ref: str | None = None,
    ) -> ScanResult:
        """Scan both line-based and semantic subscriptions."""
        line_result = self.line_detector.scan(line_subscriptions, base_ref, target_ref)
        semantic_result = self.semantic_detector.scan(semantic_subscriptions, base_ref, target_ref)

        return ScanResult(
            base_ref=base_ref,
            target_ref=target_ref or "WORKING",
            triggers=line_result.triggers + semantic_result.triggers,
            proposals=line_result.proposals + semantic_result.proposals,
            unchanged=line_result.unchanged + semantic_result.unchanged,
        )
```

---

### Step 8: Update Config Store
**Files:** `src/codesub/config_store.py`

**Changes:**
- Add methods for semantic subscription CRUD
- Update schema version handling for migration
- Add `list_semantic_subscriptions()`, `add_semantic_subscription()`, etc.

---

### Step 9: Add CLI Commands
**Files:** `src/codesub/cli.py`

**Changes:**
- Add `codesub add-semantic` command
- Add `codesub list --semantic` flag
- Update `codesub scan` to include semantic subscriptions
- Add `codesub parse` command for debugging/exploration

---

### Step 10: Add API Endpoints
**Files:** `src/codesub/api.py`

**Changes:**
- Add Pydantic schemas for semantic subscriptions
- Add CRUD endpoints for semantic subscriptions
- Update scan endpoint to include semantic results
- Add parse endpoint for construct discovery

---

### Step 11: Update Dependencies
**Files:** `pyproject.toml`

**Changes:**
```toml
[tool.poetry.dependencies]
tree-sitter = ">=0.21.0"
tree-sitter-python = ">=0.21.0"
```

---

## Testing Strategy

- [ ] **Unit tests for parser.py**
  - Test PythonParser parses functions, classes, methods, variables
  - Test nested constructs (methods inside classes)
  - Test decorated functions
  - Test error handling for malformed code

- [ ] **Unit tests for fingerprint.py**
  - Test interface_hash excludes name but includes params/decorators
  - Test body_hash ignores whitespace and comments
  - Test body_hash_normalized handles local variable renames
  - Test doc_hash changes with docstring changes

- [ ] **Unit tests for extractor.py**
  - Test extract_all finds all constructs
  - Test extract_by_fqn finds specific construct
  - Test FQN generation for nested constructs
  - Test unsupported file types return empty

- [ ] **Unit tests for matcher.py**
  - Test exact FQN match
  - Test rename detection (same body, different name)
  - Test move detection (same body, different file)
  - Test change classification (structural vs content vs cosmetic)
  - Test deleted construct detection

- [ ] **Integration tests for semantic_detector.py**
  - Test scan with semantic subscriptions in git repo
  - Test trigger on function body change
  - Test proposal on function rename
  - Test no trigger on cosmetic change
  - Test cross-file move detection

- [ ] **Integration tests for unified detector**
  - Test mixed line-based and semantic subscriptions
  - Test results are properly merged

- [ ] **CLI integration tests**
  - Test `codesub add-semantic` command
  - Test `codesub parse` command
  - Test `codesub scan` with semantic subscriptions

- [ ] **API integration tests**
  - Test semantic subscription CRUD endpoints
  - Test parse endpoint
  - Test scan includes semantic results

---

## Edge Cases Considered

- **Malformed source code**: Tree-sitter is error-tolerant; parse what we can
- **Empty files**: Return empty construct list
- **Binary files**: Skip parsing, not supported
- **Nested classes/functions**: Build correct FQN hierarchy
- **Decorators with arguments**: Include in interface_hash
- **Lambda functions**: Treat as anonymous, skip for now
- **Comprehensions**: Include in body_hash but not as separate constructs
- **Deleted files**: Mark all constructs as deleted
- **New files**: New constructs have no old match

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Tree-sitter grammar changes break parsing | Pin tree-sitter versions; add comprehensive tests |
| Fingerprint collisions cause false matches | Use SHA-256 with 16-char truncation; very low collision probability |
| Performance issues with large files | Tree-sitter is optimized for speed; add caching if needed |
| Migration breaks existing configs | Schema version migration that preserves existing line-based subscriptions |

---

## Migration Path for Existing Subscriptions

1. **Schema Migration**: When loading a v1 config:
   - Add empty `semantic_subscriptions` list
   - Save as v2
   - All existing line-based subscriptions preserved

2. **Optional Conversion**: Users can optionally convert line-based subscriptions to semantic:
   - `codesub convert-to-semantic <subscription_id>`
   - Finds the construct at the subscribed line range
   - Creates semantic subscription, deactivates line-based
   - Requires human review (may not be 1:1 mapping)

3. **Dual Mode**: Both subscription types work simultaneously
   - Scan runs both detectors
   - Results are merged
   - No forced migration
