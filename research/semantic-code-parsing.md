# Semantic Code Parsing and Tracking - Research Findings

> Last researched: 2026-01-26
> Focus: Approaches for parsing code constructs and tracking them across git commits

## Executive Summary

This research evaluates approaches for **semantic code parsing** and **tracking code constructs** (classes, functions, variables) across git changes. The goal is to support a tool that can:
- Parse Python code to find class/function/variable definitions
- Track the same construct across git commits (even if moved/renamed)
- Eventually support Java and Go

### Key Findings

1. **Tree-sitter** is the best option for multi-language parsing with excellent performance
2. **Python AST** is simplest for Python-only use cases but has limitations
3. **LibCST** excels at code transformation but is Python-only
4. **GumTree** and semantic diff tools struggle with cross-file tracking
5. **RefactoringMiner** is the gold standard for tracking refactorings across files (Java-focused)
6. **LSIF** is designed for IDE navigation, not historical tracking

---

## 1. Tree-sitter

### Overview
Tree-sitter is an **incremental parsing library** that generates concrete syntax trees (CST) for multiple programming languages. Originally created for text editors, it's now widely used in static analysis tools including GitHub's code navigation.

### Python Bindings

**Installation:**
```bash
pip install tree-sitter
pip install tree-sitter-python  # For Python support
pip install tree-sitter-languages  # Pre-built grammars for 50+ languages
```

**Key Libraries:**
- `py-tree-sitter` - Official Python bindings (v0.25.2 as of 2026)
- `tree-sitter-languages` - Pre-compiled language grammars
- Individual packages: `tree-sitter-python`, `tree-sitter-java`, `tree-sitter-go`

### Query Syntax for Finding Code Constructs

Tree-sitter uses a Lisp-style query language with pattern matching:

```python
from tree_sitter import Parser, Language
import tree_sitter_python as tspython

# Setup
PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

# Find function definitions
query = PY_LANGUAGE.query("""
(function_definition
  name: (identifier) @function.name
  parameters: (parameters) @function.params
  body: (block) @function.body)
""")

# Find class definitions
class_query = PY_LANGUAGE.query("""
(class_definition
  name: (identifier) @class.name
  body: (block) @class.body)
""")

# Find variable assignments
var_query = PY_LANGUAGE.query("""
(assignment
  left: (identifier) @var.name
  right: (_) @var.value)
""")

# Parse and query
tree = parser.parse(bytes(code, "utf8"))
captures = query.captures(tree.root_node)
```

**Query Features:**
- Field names for precise matching (e.g., `name:`, `body:`)
- Capture groups using `@capture.name` syntax
- Wildcard matching with `(_)`
- Predicate filtering for complex conditions

### Multi-Language Support

Tree-sitter provides **50+ language grammars** including:
- Python, Java, Go, JavaScript, TypeScript, Rust, C/C++
- Single interface for all languages
- Language-agnostic query patterns

**Language-specific setup:**
```python
import tree_sitter_java
import tree_sitter_go

JAVA_LANGUAGE = Language(tree_sitter_java.language())
GO_LANGUAGE = Language(tree_sitter_go.language())
```

### Performance Characteristics

- **Incremental parsing**: O(n) parsing, updates in <1ms for typical edits
- **10x faster** than regex-based syntax highlighting
- **Efficient tree diffing**: `Tree.changed_ranges()` identifies modified regions
- **Memory efficient**: Pre-compiled language binaries, no runtime dependencies
- **Java parsing speedup**: One project saw 36x improvement over JavaParser

### APIs

**Core Classes:**
- `Parser` - Configures language and parses source
- `Tree` - Root of parsed syntax tree
- `Node` - Individual syntax node with type, position, children
- `Query` - Pattern-based node searching
- `QueryCursor` - Executes queries and returns captures
- `TreeCursor` - Efficient tree traversal

**Node Operations:**
```python
node.type              # Node type (e.g., "function_definition")
node.text              # Source text as bytes
node.start_byte        # Starting byte position
node.end_byte          # Ending byte position
node.start_point       # (row, column) tuple
node.children          # Child nodes
node.child_by_field_name("name")  # Access named fields
```

**Incremental Parsing:**
```python
old_tree = parser.parse(old_code)
new_tree = parser.parse(new_code, old_tree=old_tree)  # Much faster!
changed_ranges = new_tree.changed_ranges(old_tree)
```

### Limitations

1. **TreeCursor limitation**: Can only traverse children of starting node (not full tree)
2. **Cross-file tracking**: Tree-sitter doesn't track code across files
3. **Rename detection**: No built-in support for detecting renames
4. **Requires old tree**: Incremental parsing needs previous tree state

### Use Cases for codesub

**Pros:**
✅ Multi-language support (Python, Java, Go)
✅ Extremely fast incremental parsing
✅ Robust handling of syntax errors
✅ Active development with strong ecosystem
✅ Used in production by GitHub, Neovim, Emacs

**Cons:**
❌ No built-in rename/move detection
❌ Single-file focus (no cross-file awareness)
❌ Requires manual tracking of node identity across commits

**Recommendation:** Use tree-sitter for **parsing** code constructs, but implement custom logic for **tracking** constructs across commits using fingerprinting or similarity matching.

---

## 2. Python AST Module

### Overview
Python's built-in `ast` module parses Python source code into an Abstract Syntax Tree. It's lossy (discards formatting) but provides native Python integration.

### Capabilities

**Extracting Definitions:**
```python
import ast

class DefinitionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.classes = []
        self.functions = []
        self.variables = []

    def visit_ClassDef(self, node):
        self.classes.append({
            'name': node.name,
            'lineno': node.lineno,
            'end_lineno': node.end_lineno
        })
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.functions.append({
            'name': node.name,
            'lineno': node.lineno,
            'end_lineno': node.end_lineno,
            'args': [arg.arg for arg in node.args.args]
        })
        self.generic_visit(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.variables.append({
                    'name': target.id,
                    'lineno': node.lineno
                })
        self.generic_visit(node)

# Usage
tree = ast.parse(source_code)
visitor = DefinitionVisitor()
visitor.visit(tree)
```

**Key Node Types:**
- `ast.ClassDef` - Class definitions
- `ast.FunctionDef` / `ast.AsyncFunctionDef` - Function definitions
- `ast.Assign` - Variable assignments
- `ast.Import` / `ast.ImportFrom` - Imports
- `ast.Call` - Function calls

### Limitations

1. **Stack depth crashes**: Malformed AST can crash Python interpreter (raises `RecursionError`, `MemoryError`, `ValueError`)
2. **Decorator complexity**: Decorators can be complex expressions (not just names), causing `AttributeError` if handled naively
3. **Missing source info**: If `lineno`, `end_lineno`, `col_offset` missing, `ast.get_source_segment()` returns `None`
4. **Python-only**: No support for other languages
5. **Lossy parsing**: Cannot reconstruct original source code (whitespace, comments lost)

### Performance

- **Fastest Python parser**: Native C implementation
- **Simple API**: Part of standard library, no dependencies
- **Good for analysis**: Excellent for linting, static analysis where formatting doesn't matter

### Use Cases for codesub

**Pros:**
✅ Built-in, no dependencies
✅ Fastest Python parsing
✅ Simple API for basic analysis
✅ Well-documented with extensive ecosystem

**Cons:**
❌ Python-only (no Java/Go support)
❌ Lossy (can't preserve formatting)
❌ Limited error recovery
❌ No rename/move detection

**Recommendation:** Use for **Python-only prototyping** or when multi-language support isn't needed. For production with Java/Go requirements, choose tree-sitter instead.

---

## 3. LibCST

### Overview
LibCST is a **lossless Concrete Syntax Tree** parser for Python that preserves all formatting details (whitespace, comments, parentheses). Created by Instagram, it's designed for automated code refactoring (codemods).

### What Makes LibCST Different

LibCST creates a compromise between AST and CST:
- **Lossless**: Preserves formatting, comments, whitespace
- **AST-like**: Organized around semantic meaning (not just syntax tokens)
- **Roundtrip**: Can parse → modify → print with formatting preserved

**Comparison:**

| Feature | Python AST | LibCST | Tree-sitter |
|---------|-----------|--------|-------------|
| Preserves formatting | ❌ | ✅ | ✅ |
| Python-only | ✅ | ✅ | ❌ (multi-lang) |
| Can modify code | ✅ | ✅ | ❌ (read-only) |
| Built-in | ✅ | ❌ | ❌ |
| Speed | Fastest | Slower | Fast |

### When to Use LibCST

**Use LibCST when:**
- Building codemods (automated refactoring tools)
- Need to preserve code formatting and style
- Making semantic changes while maintaining original appearance
- Building Python linters with auto-fix capabilities

**Don't use LibCST when:**
- Building compilers or type checkers (use Python AST)
- Only reading code (not modifying)
- Need multi-language support (use tree-sitter)
- Performance is critical (use Python AST)

### APIs for Finding Constructs

**Installation:**
```bash
pip install libcst
```

**Visitor Pattern:**
```python
import libcst as cst

class CodeAnalyzer(cst.CSTVisitor):
    def __init__(self):
        self.classes = []
        self.functions = []
        self.stack = []  # Track nesting

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self.classes.append(node.name.value)
        self.stack.append(node.name.value)

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self.stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        qualified_name = ".".join(self.stack + [node.name.value])
        self.functions.append(qualified_name)
        return False  # Don't traverse into function body

# Usage
module = cst.parse_module(source_code)
visitor = CodeAnalyzer()
module.visit(visitor)
```

**Transformer Pattern (for modifications):**
```python
class FunctionRenamer(cst.CSTTransformer):
    def leave_FunctionDef(
        self, original: cst.FunctionDef, updated: cst.FunctionDef
    ) -> cst.FunctionDef:
        if original.name.value == "old_name":
            return updated.with_changes(
                name=cst.Name("new_name")
            )
        return updated

# Apply transformation
new_module = module.visit(FunctionRenamer())
print(new_module.code)  # Prints modified code with formatting preserved
```

**Metadata Providers:**
- `PositionProvider` - Line/column information
- `ScopeProvider` - Variable scope analysis
- `QualifiedNameProvider` - Fully qualified names for imports

### Performance

- **Slower than Python AST**: Extra work to track whitespace
- **Production-ready**: Used at Instagram scale
- **Python 3.9+ required**
- No benchmarks available, but acceptable for most use cases

### Limitations

1. **Python-only**: No support for Java, Go, or other languages
2. **Slower parsing**: More overhead than Python AST
3. **Rust toolchain**: Required for building on unsupported platforms
4. **No cross-file tracking**: Single file focus like other parsers

### Use Cases for codesub

**Pros:**
✅ Perfect for code transformation tools
✅ Preserves formatting (useful for applying fixes)
✅ Rich metadata support
✅ Production-tested at Instagram

**Cons:**
❌ Python-only (no Java/Go support)
❌ Slower than alternatives
❌ No built-in rename/move detection
❌ Overkill if only reading code

**Recommendation:** Use LibCST if codesub needs to **apply automated fixes** to Python subscriptions. Otherwise, tree-sitter is better for multi-language support.

---

## 4. GumTree and Semantic Diff Tools

### GumTree

**Overview:**
GumTree is an AST-based diff tool that computes differences at the syntax tree level rather than text level. It can detect moved or renamed elements beyond simple insertions/deletions.

### How It Works

GumTree performs tree-to-tree differencing using:
1. **AST construction** for both versions
2. **Tree matching** to find corresponding nodes
3. **Edit script generation** with syntax-aware actions

**6 Edit Actions:**
1. Insert a node
2. Delete a node
3. Update a node label (e.g., rename)
4. Move a subtree
5. Insert a subtree
6. Delete a subtree

### Supported Languages

- C, Java, JavaScript, Python, R, Ruby
- Uses multiple generator approaches:
  - `gen.jdt` - Eclipse JDT for Java
  - `gen.javaparser` - JavaParser for Java
  - `gen.treesitter-ng` - Tree-sitter for various languages
  - `gen.antlr3` - ANTLR for custom grammars

### Rename Detection

**How renames are shown:**
Renamed identifiers appear as "Update a node label" actions:
```
Update((identifier:my_func, line 1:12 - 1:19), new_func_name)
```

**Limitation:** If matching fails, GumTree may forcefully match deleted methods to added methods, misleading reviewers into thinking methods were renamed when they weren't.

### Critical Limitations

1. **No cross-file detection**: GumTree accepts pairs of files as input and "cannot detect the move of a code fragment to another file modified in the same commit"
2. **Per-file matching**: Forces matching within single files, missing cross-file refactorings
3. **Incorrect matching**: Can produce misleading diffs when similarity is low

**Exception:** **Staged Tree Matching** extension applies GumTree across multiple files in a commit, addressing the cross-file limitation.

### CLI Usage

```bash
# Install
git clone https://github.com/GumTreeDiff/gumtree
cd gumtree
./gradlew build

# Run diff
./gumtree-*/bin/gumtree textdiff old_file.py new_file.py

# Web UI
./gumtree-*/bin/gumtree webdiff old_file.py new_file.py
```

### Related Tools

**diffsitter** (tree-sitter based):
- Creates semantic diffs using tree-sitter parsers
- Ignores formatting differences (whitespace, optional punctuation)
- Filters nodes via `include_nodes` / `exclude_nodes` config
- Uses LCS (Longest Common Subsequence) on AST leaves

**Installation:**
```bash
cargo install diffsitter
```

**Limitations:**
- Language support limited to tree-sitter parsers
- Node filtering only applies to leaf nodes
- Output not significantly more readable than traditional diff
- No high-level refactoring detection (e.g., "Extract Method")

**code-diff** (Python library):
- Fast reimplementation of GumTree algorithm
- Detects function renames in Python, Java, JavaScript
- Uses tree-sitter for parsing

```python
import code_diff as cd
output = cd.difference(source_code, target_code, lang="python")
print(output.edit_script())
```

**Example output:**
```
Update((identifier:my_func, line 1:12 - 1:19), say_helloworld)
```

**astdiff** (Basic Python tool):
- Compares ASTs and returns 0 if same, 1 if different
- Can check commits or working trees
- Much simpler than GumTree, no rename detection

### Use Cases for codesub

**Pros:**
✅ Syntax-aware diffing (ignores formatting)
✅ Detects moves and renames within files
✅ Multi-language support
✅ Well-researched algorithm

**Cons:**
❌ No cross-file tracking (critical limitation)
❌ Single-file pairs only (standard version)
❌ Incorrect matching when similarity is low
❌ Requires external process (Java-based)
❌ No built-in git integration

**Recommendation:** GumTree is **not suitable** for codesub's use case. It cannot track code moved between files in a commit. Consider **RefactoringMiner** instead (see next section).

---

## 5. RefactoringMiner

### Overview
RefactoringMiner is a research tool that detects refactorings in git commits with **cross-file awareness**. Unlike GumTree, it analyzes all modified files in a commit together, enabling detection of methods moved between files.

### Key Capabilities

**Refactoring Detection:**
- Rename Method, Move Method
- Rename Class, Move Class, Move and Rename Class
- Extract and Move Method
- Pull Up/Push Down Method
- Inline/Extract Method
- Change Method Signature

**Cross-File Awareness:**
Unlike GumTree and other AST diff tools, RefactoringMiner is "aware of changes taking place in other files modified in the same commit." This enables detection of:
- Methods moved to different files
- Classes renamed and moved
- Code extracted from one file and moved to another

### Technical Approach

RefactoringMiner uses a **threshold-free matching approach**:
- Applies all syntactically valid AST node replacements
- Matches statements only if they become textually identical after replacements
- More precise than similarity-based matching (avoids false positives)

**Advantages:**
- Automatically excludes files with identical contents
- Shows overlapping refactorings within moved code
- Can generate diffs for any pair of modified/added/deleted files

### Installation & Requirements

**Requirements:**
- Java 17 or newer (since v3.0.0)
- Gradle 7.4 or newer

**Installation:**
```bash
git clone https://github.com/tsantalis/RefactoringMiner
cd RefactoringMiner
./gradlew build
```

### Usage

**CLI:**
```bash
# Analyze a commit
./gradlew run -Pargs="-c /path/to/repo commit-sha"

# Analyze a range of commits
./gradlew run -Pargs="-bc /path/to/repo commit1 commit2"

# Analyze all commits
./gradlew run -Pargs="-a /path/to/repo branch"
```

**API (Java):**
```java
GitService gitService = new GitServiceImpl();
GitHistoryRefactoringMiner miner = new GitHistoryRefactoringMinerImpl();

miner.detectAtCommit(repository, commitId, new RefactoringHandler() {
    @Override
    public void handle(String commitId, List<Refactoring> refactorings) {
        for (Refactoring ref : refactorings) {
            System.out.println(ref.toString());
        }
    }
});
```

### Output Format

```json
{
  "commits": [
    {
      "sha1": "abc123",
      "refactorings": [
        {
          "type": "Move Method",
          "description": "Move Method calculateTotal() from class OrderService to class PriceCalculator",
          "leftSideLocations": [
            {
              "filePath": "src/OrderService.java",
              "startLine": 42,
              "endLine": 58
            }
          ],
          "rightSideLocations": [
            {
              "filePath": "src/PriceCalculator.java",
              "startLine": 15,
              "endLine": 31
            }
          ]
        }
      ]
    }
  ]
}
```

### Limitations

1. **Java-focused**: Primarily designed for Java (uses Eclipse JDT parser)
2. **Research tool**: Not production-ready for continuous integration
3. **Performance**: Can be slow on large repositories with many commits
4. **Language support**: Limited to languages with mature AST parsers (mainly Java)
5. **Git-only**: Requires git repository structure

### Use Cases for codesub

**Pros:**
✅ **Cross-file tracking** (critical for codesub)
✅ Detects renamed and moved methods
✅ Git-integrated (works with commits)
✅ Threshold-free matching (precise)
✅ Production-tested in research

**Cons:**
❌ Java-focused (limited Python/Go support)
❌ Research tool (may lack polish)
❌ Performance concerns on large repos
❌ Requires Java runtime

**Recommendation:** RefactoringMiner's approach is **ideal for codesub**, but it's Java-focused. Consider implementing a **similar cross-file approach** using tree-sitter for Python/Java/Go support.

---

## 6. LSIF (Language Server Index Format)

### Overview
LSIF is a **graph-based format** for storing language server knowledge, enabling rich code navigation (Go to Definition, Find References) without local source code or running a language server.

### Purpose

LSIF is designed for:
- Code browsing in web UIs (GitHub, GitLab)
- Pull request review with code navigation
- Static code analysis without compilation
- IDE-like features in non-IDE environments

### How It Works

**Graph Structure:**
- **Vertices**: Documents, code ranges, hover info, definition results
- **Edges**: Relationships (containment, references, definitions)

**Example data:**
```json
{"id": 1, "type": "vertex", "label": "document", "uri": "file:///path/to/file.py"}
{"id": 2, "type": "vertex", "label": "range", "start": {"line": 5, "character": 4}}
{"id": 3, "type": "edge", "label": "contains", "outV": 1, "inV": 2}
```

### Indexed Data

LSIF supports:
- Document symbols and folding ranges
- Hover information (type, documentation)
- Go to Definition/Declaration/Type Definition
- Find All References
- Go to Implementation
- Document links

**Note:** LSIF "doesn't contain any program symbol information" in the sense that it models LSP request results, not semantic analysis.

### Available Tools

**Generators:**
- `lsif-java` - Java indexer (Microsoft)
- `lsif-node` - TypeScript/JavaScript indexer
- `lsif-go` - Go indexer
- Various community indexers for Python, C++, etc.

**Consumers:**
- VS Code extension for LSIF
- Sourcegraph code intelligence
- GitHub code navigation

### Limitations for Code Tracking

1. **Point-in-time**: LSIF indexes a single workspace snapshot, not history
2. **No cross-commit tracking**: Not designed for tracking code evolution
3. **Static navigation**: Enables "Go to Definition" but not "Track this function across commits"
4. **Large file size**: Complete LSIF dumps can be gigabytes for large projects

### Use Cases for codesub

**Pros:**
✅ Multi-language support (via LSP)
✅ Standardized format
✅ Rich semantic information

**Cons:**
❌ **Not designed for history tracking**
❌ Point-in-time snapshots only
❌ Large file sizes
❌ Complex graph format
❌ Requires language-specific indexers

**Recommendation:** LSIF is **not suitable** for codesub. It's designed for code navigation, not tracking constructs across commits.

---

## 7. Additional Approaches

### Code Fingerprinting / Semantic Hashing

**Concept:** Generate stable hashes of code constructs based on semantic features, enabling tracking across renames and minor modifications.

**Techniques:**

1. **Syntax Tree Fingerprinting:**
   - Hash AST structure (node types, relationships)
   - Normalize identifier names (e.g., replace with placeholders)
   - Creates fingerprints stable across renames

2. **Semantic Hashing (for binaries):**
   - Extract control flow graphs (CFG)
   - Hash instruction sequences
   - Used in BinSign, semantic_firewall projects

3. **Locality-Sensitive Hashing (LSH):**
   - Hash similar code to similar values
   - Enables approximate matching
   - Used for clone detection

**Example Approach:**
```python
import hashlib
import ast

def fingerprint_function(func_node: ast.FunctionDef) -> str:
    """Generate semantic fingerprint for a function."""
    # Extract structural features
    features = {
        'num_params': len(func_node.args.args),
        'num_statements': len(func_node.body),
        'calls': [n.func.id for n in ast.walk(func_node)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)],
        'control_flow': count_control_structures(func_node)
    }

    # Hash normalized features
    feature_string = str(sorted(features.items()))
    return hashlib.sha256(feature_string.encode()).hexdigest()
```

**Tools:**
- `semantic_firewall` (Go) - Fingerprints Go functions using SSA analysis
- Research papers on syntax tree fingerprinting
- Clone detection tools (e.g., SourcererCC, CCFinderX)

**Use Case for codesub:**

Fingerprinting could enable tracking functions across commits:
1. Parse code at each commit using tree-sitter
2. Generate fingerprint for each function/class
3. Match fingerprints across commits
4. Detect moved/renamed constructs by fingerprint similarity

**Pros:**
✅ Detects renames (name not included in fingerprint)
✅ Robust to minor modifications
✅ Works across files

**Cons:**
❌ False positives (similar code, different purpose)
❌ False negatives (significant refactoring changes fingerprint)
❌ Requires tuning similarity thresholds
❌ No standard library/tool

### Git's Built-in Rename Detection

Git has rename detection via `git diff -M` and `git log --follow`:

```bash
# Detect renames in diff
git diff -M HEAD~1 HEAD

# Follow file history across renames
git log --follow -- path/to/file.py
```

**How it works:**
- Hashes file content
- Detects files with >50% similarity (configurable)
- Works at file level, not function level

**Limitations:**
- File-level only (not function/class level)
- No cross-file detection for extracted code
- Similarity-based (can miss semantic renames)

---

## Recommendations for codesub

### Parsing Approach

**Use Tree-sitter** for parsing code constructs:

**Rationale:**
1. ✅ Multi-language support (Python, Java, Go)
2. ✅ Fast incremental parsing
3. ✅ Robust error handling
4. ✅ Active development, strong ecosystem
5. ✅ Used in production by GitHub, major editors

**Implementation:**
```python
from tree_sitter import Parser, Language
import tree_sitter_python, tree_sitter_java, tree_sitter_go

LANGUAGES = {
    'python': Language(tree_sitter_python.language()),
    'java': Language(tree_sitter_java.language()),
    'go': Language(tree_sitter_go.language())
}

def parse_file(file_path: str, language: str):
    parser = Parser(LANGUAGES[language])
    with open(file_path, 'rb') as f:
        code = f.read()
    return parser.parse(code)

def find_functions(tree, language: str):
    """Extract function definitions from tree."""
    query_patterns = {
        'python': '(function_definition name: (identifier) @name)',
        'java': '(method_declaration name: (identifier) @name)',
        'go': '(function_declaration name: (identifier) @name)'
    }

    query = LANGUAGES[language].query(query_patterns[language])
    captures = query.captures(tree.root_node)
    return [node.text.decode('utf8') for name, node in captures]
```

### Tracking Approach

**Implement a hybrid approach** combining:

1. **Tree-sitter for parsing** at each git commit
2. **Semantic fingerprinting** for matching constructs across commits
3. **Cross-file awareness** (analyze all modified files together like RefactoringMiner)
4. **Git diff context** for detecting file renames

**Architecture:**

```
┌─────────────────────────────────────────────┐
│ Subscription Manager                        │
│ - Subscriptions stored with fingerprints    │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│ Change Detector (per commit)                │
│ 1. Get modified files (git diff --name-only)│
│ 2. Parse old & new versions (tree-sitter)   │
│ 3. Extract constructs (functions, classes)  │
│ 4. Generate fingerprints                    │
│ 5. Match across files                       │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│ Subscription Updater                        │
│ - Match fingerprints to subscriptions       │
│ - Update line ranges                        │
│ - Flag moved/renamed constructs             │
└─────────────────────────────────────────────┘
```

**Fingerprinting Strategy:**

For Python functions:
```python
def fingerprint_function(node, source_code):
    """Generate semantic fingerprint for function."""
    features = {
        'num_params': count_parameters(node),
        'num_statements': count_statements(node),
        'return_type': extract_return_type(node),
        'called_functions': extract_function_calls(node),
        'control_structures': count_control_structures(node),
        'body_hash': hash_normalized_body(node)  # Normalize variable names
    }
    return hash(frozenset(features.items()))
```

For Java methods:
```python
def fingerprint_method(node, source_code):
    """Generate semantic fingerprint for Java method."""
    features = {
        'signature_hash': hash_signature(node),  # Types, not names
        'num_statements': count_statements(node),
        'method_calls': extract_method_calls(node),
        'field_accesses': extract_field_accesses(node),
        'control_flow_hash': hash_control_flow(node)
    }
    return hash(frozenset(features.items()))
```

**Matching Algorithm:**

```python
def match_constructs(old_constructs, new_constructs, threshold=0.85):
    """Match constructs across commits using fingerprints."""
    matches = []

    for old_construct in old_constructs:
        best_match = None
        best_similarity = 0

        for new_construct in new_constructs:
            similarity = compute_similarity(
                old_construct.fingerprint,
                new_construct.fingerprint
            )

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = new_construct

        if best_similarity >= threshold:
            matches.append((old_construct, best_match, best_similarity))

    return matches
```

### Implementation Phases

**Phase 1: Basic Tree-sitter Integration**
- Parse Python files using tree-sitter
- Extract function/class definitions
- Store construct metadata with subscriptions

**Phase 2: Fingerprinting**
- Implement semantic fingerprinting
- Test on real refactoring examples
- Tune similarity thresholds

**Phase 3: Cross-File Tracking**
- Analyze all modified files in a commit together
- Match constructs across files
- Detect moved/renamed constructs

**Phase 4: Multi-Language**
- Add Java support (tree-sitter-java)
- Add Go support (tree-sitter-go)
- Generalize fingerprinting approach

---

## Summary Table

| Approach | Multi-Lang | Cross-File | Rename Detection | Performance | Recommendation |
|----------|-----------|------------|------------------|-------------|----------------|
| **Tree-sitter** | ✅ Yes | ❌ No | ❌ No | ⚡ Excellent | **Use for parsing** |
| **Python AST** | ❌ Python-only | ❌ No | ❌ No | ⚡⚡ Best | Prototype only |
| **LibCST** | ❌ Python-only | ❌ No | ❌ No | 🐌 Slower | Use for codemods |
| **GumTree** | ✅ Yes | ❌ No | ⚠️ Partial | ⚡ Good | Not suitable |
| **RefactoringMiner** | ⚠️ Java-focused | ✅ Yes | ✅ Yes | 🐌 Slow | Learn from approach |
| **LSIF** | ✅ Yes | ❌ No | ❌ No | ⚡ Good | Not for tracking |
| **Fingerprinting** | ✅ Yes | ✅ Yes | ✅ Yes | ⚡ Good | **Use for tracking** |

**Final Recommendation:**
- **Parse with tree-sitter** (multi-language, fast, robust)
- **Track with semantic fingerprinting** (cross-file, rename detection)
- **Inspire approach from RefactoringMiner** (cross-file awareness)
- **Start with Python, expand to Java/Go** (incremental implementation)

---

## Sources

### Tree-sitter
- [py-tree-sitter GitHub](https://github.com/tree-sitter/py-tree-sitter)
- [Query Documentation](https://tree-sitter.github.io/py-tree-sitter/classes/tree_sitter.Query.html)
- [tree-sitter-languages PyPI](https://pypi.org/project/tree-sitter-languages/)
- [Diving into Tree-Sitter Tutorial](https://dev.to/shrsv/diving-into-tree-sitter-parsing-code-with-python-like-a-pro-17h8)
- [Tree-sitter Official Docs](https://tree-sitter.github.io/)
- [TreeSitter Parsing Blog](https://symflower.com/en/company/blog/2023/parsing-code-with-tree-sitter/)

### Python AST & LibCST
- [Python AST Documentation](https://docs.python.org/3/library/ast.html)
- [LibCST GitHub](https://github.com/Instagram/LibCST)
- [LibCST Documentation](https://libcst.readthedocs.io/)
- [Why LibCST?](https://libcst.readthedocs.io/en/latest/why_libcst.html)
- [LibCST Tutorial](https://libcst.readthedocs.io/en/latest/tutorial.html)

### GumTree & Semantic Diff
- [GumTree GitHub](https://github.com/GumTreeDiff/gumtree)
- [diffsitter GitHub](https://github.com/afnanenayet/diffsitter)
- [code-diff GitHub](https://github.com/cedricrupb/code_diff)
- [astdiff PyPI](https://pypi.org/project/astdiff/)
- [Semantic Code Diff Review](https://mgx.dev/insights/a-comprehensive-review-of-semantic-code-diff-analysis-from-foundations-to-future-trends/f78dabc3a2394fb18d57f3e8736acbb7)
- [Novel Refactoring AST Tool (PDF)](https://users.encs.concordia.ca/~nikolaos/publications/TOSEM_2024.pdf)

### RefactoringMiner
- [RefactoringMiner GitHub](https://github.com/tsantalis/RefactoringMiner)
- [Tracking Java Methods with Git (PDF)](https://arxiv.org/pdf/2003.05336)

### LSIF
- [LSIF Overview](https://microsoft.github.io/language-server-protocol/overviews/lsif/overview/)
- [LSIF Specification 0.5.0](https://microsoft.github.io/language-server-protocol/specifications/lsif/0.5.0/specification/)
- [LSIF Blog Post](https://code.visualstudio.com/blogs/2019/02/19/lsif)

### Code Fingerprinting
- [semantic_firewall GitHub](https://github.com/BlackVectorOps/semantic_firewall)
- [Binary Code Fingerprinting Survey](https://dl.acm.org/doi/10.1145/3486860)
- [Syntax Tree Fingerprinting Paper](https://www.researchgate.net/publication/221219530_Syntax_tree_fingerprinting_for_source_code_similarity_detection)

### Comparisons
- [Tree-sitter vs LSP](https://byteiota.com/tree-sitter-vs-lsp-why-hybrid-ide-architecture-wins/)
- [code_ast GitHub](https://github.com/cedricrupb/code_ast)
