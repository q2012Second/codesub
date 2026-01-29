# Semantic Code Subscriptions - Research Document

## Problem Reformulation

### Current State
The codesub tool tracks **line-based subscriptions**: users subscribe to specific line ranges (e.g., `models.py:42-50`). When code changes:
- If lines within the range are modified → **trigger** notification
- If lines shift due to additions/deletions above → **propose** line number update
- If file is renamed → **propose** path update

### Limitation
Line numbers are **fragile identifiers**. They don't represent the actual semantic intent:
- User wants to track the `Address` class definition, not "lines 42-50"
- Adding a docstring above the class shifts line numbers, but the tracked code is unchanged
- Refactoring that moves a class to another file loses the subscription entirely

### Desired State
Track **semantic code constructs** instead of line numbers:

| Construct Type | Example | Python Syntax |
|----------------|---------|---------------|
| Class definition | `class Address` | `class Address:` |
| Function/method | `def validate_street()` | `def validate_street(...):` |
| Variable/constant | `MAX_STREET_LENGTH = 100` | assignment at module/class level |
| Class attribute | `Address.street` | attribute definition in `__init__` or class body |

### Key Requirements

1. **Identity Tracking**: Recognize the same construct across changes
   - Class renamed from `Address` to `MailingAddress` → still the same construct (maybe with notification)
   - Class moved to different file → still track it
   - Class body modified → trigger notification

2. **Change Classification**:
   - **Structural changes**: signature changed, type changed, renamed → TRIGGER
   - **Content changes**: implementation modified → TRIGGER
   - **Location changes**: moved to different file/line → UPDATE subscription, no trigger
   - **Cosmetic changes**: formatting, comments → NO action

3. **Language Support Strategy**:
   - Phase 1: Python-only (POC)
   - Phase 2: Add Java/Go support
   - Goal: Same subscription model, language-specific parsers

### Technical Challenges

1. **Parsing**: How to extract semantic constructs from source code?
2. **Identity**: How to uniquely identify a construct (name alone? qualified name? signature?)
3. **Tracking**: How to find the "same" construct in a new version of code?
4. **Diff Integration**: How to determine what changed in semantic terms from git diff?

---

## Research Prompt for External LLM

Use this prompt with Claude.ai, ChatGPT, or another LLM to research approaches:

---

### PROMPT START

**Context**: I'm building a code subscription tool that notifies developers when code they depend on changes. Currently it uses line-number based tracking, but I want to upgrade to semantic tracking of code constructs (classes, functions, variables).

**Goal**: Research approaches for tracking semantic code constructs across git changes.

**Specific Questions**:

1. **Parsing Approaches**
   - What are the main approaches to parse source code and extract semantic constructs (classes, functions, variables)?
   - Compare: Native AST (ast module), Tree-sitter, Language Server Protocol (LSP), regex-based
   - What are trade-offs for each in terms of: accuracy, language support, complexity, dependencies?

2. **Identity and Matching**
   - How can I uniquely identify a code construct across versions?
   - Options: fully qualified name, signature hash, content hash, structural similarity
   - How do refactoring tools (IDE rename, move) solve this problem?

3. **Diff-Based vs. Snapshot-Based**
   - Should I analyze git diffs semantically, or compare two snapshots of parsed AST?
   - What tools exist for semantic diff (e.g., GumTree, difftastic, semantic-diff)?

4. **Existing Tools and Libraries**
   - What Python libraries exist for code analysis? (ast, tree-sitter-python, LibCST, Jedi, rope)
   - What language-agnostic tools could help? (Tree-sitter, LSIF, universal-ctags)

5. **Cross-Language Strategy**
   - How can I design a system that works for Python now but extends to Java/Go later?
   - What abstraction layer makes sense?

**Constraints**:
- Static analysis only (no runtime execution)
- Must work with local git repositories
- Should handle partial/invalid code gracefully
- Performance matters (will run on each commit/MR)

**Output Requested**:
For each approach, provide:
- Brief description
- Key libraries/tools
- Pros (✓) and Cons (✗)
- Recommendation for my use case

### PROMPT END

---

## Candidate Approaches (To Be Researched)

### Approach 1: Native AST Parsing (Python `ast` module)
- Parse Python code using built-in `ast` module
- Walk AST to find class/function/variable definitions
- Store qualified names as subscription targets

### Approach 2: Tree-sitter
- Use tree-sitter parsers (available for 100+ languages)
- Query-based extraction of constructs
- Single abstraction layer for multiple languages

### Approach 3: LibCST (Concrete Syntax Tree)
- Python library that preserves formatting/comments
- Better for code modification, but heavier

### Approach 4: Language Server Protocol (LSP)
- Use language servers to get symbol information
- Rich semantic info (types, references)
- Heavyweight, requires running server

### Approach 5: Semantic Diff Tools
- GumTree: AST-based diff algorithm
- Difftastic: structural diff tool
- Analyze what semantically changed between versions

### Approach 6: Hybrid Line + Semantic
- Keep line-based as fallback
- Add semantic layer on top
- Subscription specifies both: `Address class at models.py:42`

---

## Evaluation Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Accuracy | High | Correctly identifies constructs and changes |
| Language extensibility | High | Easy to add Java/Go support |
| Robustness | Medium | Handles edge cases (syntax errors, partial code) |
| Performance | Medium | Fast enough for CI/CD integration |
| Complexity | Medium | Reasonable implementation effort |
| Dependencies | Low | Minimize external dependencies |

---

---

## Research Findings Summary

### Parsing Tools Comparison

| Tool | Languages | Speed | Error Recovery | Dependencies | Best For |
|------|-----------|-------|----------------|--------------|----------|
| **Tree-sitter** | 50+ | ⚡ Excellent | ✅ Robust | External | Multi-language parsing |
| **Python `ast`** | Python only | ⚡⚡ Fastest | ❌ Crashes | Built-in | Quick Python-only prototypes |
| **LibCST** | Python only | 🐌 Slower | ✅ Good | External | Code transformations |

### Tracking/Matching Tools Comparison

| Tool | Cross-File | Rename Detection | Language | Best For |
|------|-----------|------------------|----------|----------|
| **GumTree** | ❌ No | ⚠️ Within file | Multi | Single-file semantic diff |
| **RefactoringMiner** | ✅ Yes | ✅ Yes | Java only | Gold standard approach |
| **Git `-M`** | ❌ File-level | ✅ File rename | Any | File renames only |
| **Fingerprinting** | ✅ Yes | ✅ Yes | Any | Custom tracking |

### Key Insight

**No existing tool solves the full problem.** RefactoringMiner does cross-file tracking but only for Java. Tree-sitter parses everything but doesn't track. The solution is to **combine tree-sitter parsing with custom fingerprinting**.

---

## Concrete Approach Options

### Option A: Tree-sitter + Fingerprinting (Recommended)

**Architecture:**
```
Subscription storage:
  - qualified_name: "module.ClassName.method_name"
  - fingerprint: semantic_hash_of_structure
  - file: "path/to/file.py"
  - line_range: (42, 58)

Change detection:
  1. Parse all modified files (old + new versions) with tree-sitter
  2. Extract constructs (class, function, variable definitions)
  3. Generate fingerprints for each construct
  4. Match fingerprints across old→new to find moved/renamed
  5. Update subscriptions accordingly
```

**Fingerprint composition (for functions):**
- Number and types of parameters
- Return type annotation
- Number of statements
- Called function names (normalized)
- Control flow structure (if/for/while counts)
- Body hash with identifiers normalized

**Pros:**
- ✅ Multi-language support via tree-sitter
- ✅ Cross-file tracking via fingerprints
- ✅ Rename detection (name excluded from fingerprint)
- ✅ Move detection (file path excluded from fingerprint)

**Cons:**
- ❌ Custom fingerprinting requires tuning
- ❌ False positives possible (similar code)
- ❌ Significant refactoring may break matching

**Implementation complexity:** Medium-High

---

### Option B: Python AST + Qualified Names (Python-only, simpler)

**Architecture:**
```
Subscription storage:
  - qualified_name: "module.ClassName.method_name"
  - signature: "method_name(arg1: str, arg2: int) -> bool"
  - file: "path/to/file.py"
  - line_range: (42, 58)

Change detection:
  1. Parse modified files with Python ast module
  2. Build symbol table (class.method → location)
  3. Compare old vs new symbol tables
  4. Match by qualified name
  5. If name not found, fall back to signature matching
```

**Pros:**
- ✅ No external dependencies
- ✅ Simpler implementation
- ✅ Handles moves within same module automatically
- ✅ Faster development

**Cons:**
- ❌ Python only (no Java/Go)
- ❌ Cross-file tracking limited to same-name matches
- ❌ No rename detection (unless signature matches)

**Implementation complexity:** Low-Medium

---

### Option C: Hybrid Line + Semantic (Incremental upgrade)

**Architecture:**
```
Subscription storage (extended current model):
  - path: "path/to/file.py"
  - start_line: 42
  - end_line: 58
  - semantic_target: {
      type: "function",
      name: "validate_street",
      parent: "Address",
      signature: "(self, value: str) -> bool"
    }

Change detection:
  1. Use current line-based detection
  2. If trigger detected, verify semantic target still exists
  3. If semantic target moved, update line range
  4. If semantic target renamed, propose update with confidence
```

**Pros:**
- ✅ Incremental upgrade to existing system
- ✅ Backward compatible
- ✅ Line-based as fallback
- ✅ Can add language support gradually

**Cons:**
- ❌ Two sources of truth (lines + semantic)
- ❌ More complex state management
- ❌ May miss changes if semantic target changes

**Implementation complexity:** Medium

---

### Option D: GumTree-based Diff Analysis

**Architecture:**
```
Use GumTree/code-diff to semantically diff old vs new file:
  1. Run semantic diff on each changed file
  2. Parse diff output for rename/move/update actions
  3. Match actions to subscriptions
  4. No cross-file support (limitation accepted)
```

**Pros:**
- ✅ Existing tool does heavy lifting
- ✅ Well-tested algorithms
- ✅ Multi-language via tree-sitter backend

**Cons:**
- ❌ No cross-file tracking
- ❌ External Java dependency (for GumTree)
- ❌ Limited control over matching

**Implementation complexity:** Low (but limited capability)

---

## Recommendation Matrix

| Requirement | Option A | Option B | Option C | Option D |
|-------------|----------|----------|----------|----------|
| Track Python functions | ✅ | ✅ | ✅ | ✅ |
| Track Java methods | ✅ | ❌ | ⚠️ Later | ✅ |
| Cross-file moves | ✅ | ⚠️ Limited | ❌ | ❌ |
| Rename detection | ✅ | ⚠️ Limited | ⚠️ Limited | ✅ |
| Implementation effort | High | Low | Medium | Low |
| Maintenance complexity | Medium | Low | High | Low |

---

## Suggested Phased Approach

**Phase 1: Python Semantic Subscriptions (Option B)**
- Use Python `ast` module
- Store qualified names (e.g., `Address.validate_street`)
- Track by name matching
- Fallback to line-based if name not found
- Deliverable: Python-specific semantic subscriptions work

**Phase 2: Add Fingerprinting for Move Detection**
- Add fingerprint computation using `ast` tree structure
- Enable cross-file detection for Python
- Deliverable: Python moved functions are tracked

**Phase 3: Migrate Parsing to Tree-sitter**
- Replace `ast` with `tree-sitter-python`
- Keep same fingerprinting logic
- Deliverable: Architecture ready for multi-language

**Phase 4: Add Java/Go Support**
- Add `tree-sitter-java` and `tree-sitter-go`
- Implement language-specific queries
- Deliverable: Multi-language semantic subscriptions

---

## Next Steps

1. [ ] Choose approach (A, B, C, or D) or confirm phased approach
2. [ ] Design subscription model extension for semantic targets
3. [ ] Implement basic Python construct extraction
4. [ ] Create test cases for move/rename scenarios
5. [ ] Build change detection logic
