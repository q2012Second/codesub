Below is a research-oriented, implementation-leaning overview of semantic construct tracking across git history, optimized for your constraints (static-only, local repos, partial/invalid code tolerance, performance per commit/MR).

⸻

Recommended direction for your use case

A practical, high-signal architecture is a hybrid:
	1.	Use git diff only to narrow scope (which files changed, and detect file renames with -M), not as your primary semantic engine.  ￼
	2.	Parse “before” and “after” snapshots of changed files into a syntax tree that can survive syntax errors (Tree-sitter is the strongest default for this). Tree-sitter is explicitly designed to be fast and robust “even in the presence of syntax errors.”  ￼
	3.	Extract constructs into a language-neutral index (classes, functions, variables, methods, etc.), compute multiple fingerprints per construct, and run a matching pipeline (exact → heuristic → fuzzy).
	4.	Optionally add a “semantic intelligence” tier later (LSP / SCIP / LSIF) when you need name-resolution, cross-file references, or “rename refactoring” certainty. LSP provides definition/reference-like features, and LSIF/SCIP persist that kind of knowledge.  ￼

This gives you:
	•	Graceful degradation on broken code (Tree-sitter error recovery).
	•	Good performance (parse only changed files; trees are fast).
	•	Cross-language extensibility (Tree-sitter + per-language extractors).

⸻

1) Parsing approaches

You asked to compare: Native AST (ast), Tree-sitter, LSP, regex-based.

A. Native AST (Python ast module)

Description
Use the language’s official parser/AST representation (in Python: ast.parse) to build an AST and then walk it to extract ClassDef, FunctionDef, assignments, etc. The stdlib ast module exposes Python’s abstract syntax grammar.  ￼

Key libraries/tools
	•	Python: ast (stdlib)  ￼
	•	(Adjacent) tokenize for lexical scanning when you need comment/whitespace handling  ￼

Pros
	•	✓ High accuracy for valid code: the grammar matches the interpreter’s view.
	•	✓ Zero extra dependencies (stdlib).
	•	✓ Fast and simple for Python-only POC.

Cons
	•	✗ Does not handle invalid/partial code gracefully (a syntax error can stop parsing; you’ll need fallback strategies).
	•	✗ Python-only (each language needs its own parser / AST library).
	•	✗ AST loses formatting trivia (comments/whitespace), which matters if you want to ignore “cosmetic” edits without extra work.

Recommendation (your use case)
Use ast as a high-precision backend when parsing succeeds, but don’t rely on it alone given your “partial/invalid code gracefully” requirement. It’s best paired with a tolerant parser (Tree-sitter or Parso) as a fallback.

⸻

B. Tree-sitter (multi-language concrete syntax tree)

Description
Tree-sitter is a parser generator + incremental parsing library that builds a concrete syntax tree and is designed to be fast and “robust enough to provide useful results even in the presence of syntax errors.”  ￼
Even though it’s famous for incremental editor use, you can parse snapshots per commit just fine.

Key libraries/tools
	•	Core docs + bindings: Tree-sitter  ￼
	•	Python bindings: tree-sitter package  ￼ and py-tree-sitter docs  ￼
	•	Bundled grammars: tree-sitter-language-pack / tree-sitter-languages  ￼
	•	Per-language grammar (example): tree-sitter-python  ￼

Pros
	•	✓ Best-in-class tolerance for incomplete/broken code (critical for MRs/partial commits).  ￼
	•	✓ Cross-language: one parsing API, many grammars.  ￼
	•	✓ Good performance target: designed to parse “on every keystroke.”  ￼
	•	✓ You can extract constructs with Tree-sitter queries (stable patterns per language).

Cons
	•	✗ Concrete syntax, not “resolved semantics”: you get structure, but not full name binding/type info unless you build it.
	•	✗ Grammar quality varies by language/version (some grammars lag new syntax).
	•	✗ You must maintain per-language extraction logic (queries / node kinds).

Recommendation (your use case)
This is the best default parsing layer given your constraints. Use Tree-sitter as the universal parser, then implement Python-specific extraction first and reuse the same framework for Java/Go later.

⸻

C. Language Server Protocol (LSP)

Description
Instead of parsing yourself, you run a language server and ask it for document/workspace symbols, definitions, references, etc. LSP is a protocol between editor/IDE and a language server providing “go to definition, find all references” and similar features.  ￼

Key libraries/tools
	•	Any language server: e.g., pyright/pylance ecosystem, gopls, jdtls, etc. (varies by language)
	•	LSP spec:  ￼
	•	Persisted alternatives: LSIF and SCIP store code intelligence computed by servers/indexers.  ￼

Pros
	•	✓ Highest semantic quality ceiling: symbol hierarchies, references, rename support (depends on server).
	•	✓ Refactoring-aware operations are “native” to language tooling stacks.
	•	✓ Cross-language strategy if you treat “language server” as the backend contract.

Cons
	•	✗ Operational complexity: managing servers, workspaces, configs, per-language quirks.
	•	✗ Performance and determinism can be harder (servers may index the whole workspace; caching is nontrivial).
	•	✗ Partial/invalid code handling varies; some servers degrade poorly.
	•	✗ Often requires build/config/type environment for high quality.

Recommendation (your use case)
Treat LSP as an optional “Tier 2” enhancement later—especially if you want refactoring detection confidence (rename/move + update references) or cross-file symbol resolution. For a performant per-commit pipeline, Tree-sitter snapshots are usually simpler.

⸻

D. Regex-based / text heuristics

Description
Extract constructs by matching textual patterns like ^class ...: or ^def ...\( and assignments.

Key libraries/tools
	•	Python re, custom tokenizers
	•	Possibly line-based + indentation heuristics (Python)

Pros
	•	✓ Very fast and dependency-free.
	•	✓ Works on invalid code (because it doesn’t parse).

Cons
	•	✗ Low accuracy: breaks on decorators, nested defs, multiline signatures, strings that look like code, unusual formatting, etc.
	•	✗ Hard to reliably get scope/qualified names.
	•	✗ Refactoring/move tracking becomes guessy.

Recommendation (your use case)
Use regex/token heuristics only as a fallback when parsing fails completely, or for cheap prefiltering (e.g., “does this file contain any def at all?”). Don’t use it as your primary extractor.

⸻

2) Identity and matching of constructs across versions

This is the core difficulty: the “same construct” must survive moves and renames, and you want to classify changes into location/content/structural/cosmetic.

What “unique identity” can mean in practice

You won’t get a perfect universally-stable ID from syntax alone, so the practical approach is:
	•	Keep a stable subscription ID (your internal UUID).
	•	Maintain a mapping from subscription → “current best-matched construct” each revision.
	•	When mapping breaks, fall back to fuzzy matching and record confidence.

Identity options you listed (and how to use them)

A. Fully Qualified Name (FQN / qualname)

Idea: module.Class.method (Python: module path + nested classes/functions).
	•	✓ Great for unchanged names.
	•	✗ Breaks on rename/move (exactly the cases you care about).

Use it as: your first-pass key and human-readable label.

⸻

B. Signature hash

Idea: hash of “interface shape”:
	•	kind (function/method/class)
	•	parameters (names? count? defaults?)
	•	decorators
	•	return annotation (if present)
	•	✓ Stable across internal body edits.
	•	✓ Helps classify “structural changes” (signature changed).
	•	✗ Still breaks on move; and renames if name included.

Tip: compute two signature hashes:
	•	Public signature hash: excludes the symbol name (rename-resistant).
	•	Full signature hash: includes name (useful for exact match and for “rename occurred” classification).

⸻

C. Content hash (normalized)

Idea: hash of the construct body after normalization.

Normalization choices matter:
	•	ignore whitespace/comments (cosmetic changes)
	•	optionally ignore docstrings (depends on whether you treat doc updates as meaningful)
	•	optionally alpha-rename local variables (rename-resistant within body)
	•	✓ Survives file moves (content unchanged).
	•	✓ Strong for tracking moved blocks.
	•	✗ Any implementation change changes the hash (which might be what you want for triggering notifications).

Best practice: maintain multiple hashes:
	•	format-insensitive body hash (ignore whitespace/comments)
	•	semantic-ish body hash (ignore local identifier renames if you implement alpha-normalization)
	•	doc hash (docstring/comments separately, so you can treat doc changes as cosmetic or not)

If you’re in Python, tokenize can help strip comments reliably at the token level.  ￼

⸻

D. Structural similarity (tree similarity / edit distance)

Idea: compare AST/CST subtrees with a similarity score.
	•	✓ Most robust for rename/move + small edits.
	•	✗ More CPU; must be used after candidate narrowing.

Use it as: your last-resort matcher, restricted to candidates in changed/renamed files.

⸻

How IDE refactoring tools “solve” rename/move

IDEs don’t usually need a cross-version stable ID. They solve it differently:
	1.	In a single snapshot, the IDE builds a syntax tree + symbol table (name resolution).
	2.	When you rename a symbol, it finds all references that resolve to that declaration and edits them consistently (rename refactoring).
	3.	When you move code, it updates imports/usages based on resolved symbol references.

Conceptually, they track identity as “the declaration node that references resolve to,” not as a persistent ID across commits. LSP formalizes access to these capabilities (definition, references, symbols, etc.).  ￼

If you want cross-version refactoring awareness like “this method was renamed,” you can:
	•	implement heuristic matching yourself (snapshot+fingerprints), or
	•	use refactoring-detection tools (next section), or
	•	use indexers like SCIP that emit stable-ish symbol identifiers for navigation (still name/path-derived, but standardized).  ￼

⸻

A practical matching pipeline (works well in subscription systems)

Here’s a proven multi-stage approach:
	1.	Scope restriction
	•	Use git diff --name-only (+ -M for renames) to get candidate files. Git’s rename detection is similarity-based and configurable.  ￼
	2.	Exact match
	•	Match by (language, kind, FQN, full signature hash).
	3.	Rename-resistant match
	•	Match by (language, kind, parent FQN, public signature hash, body hash) with high confidence.
	4.	Move detection
	•	If file renamed, search in renamed target first (using -M results).
	•	If not found, search in all changed files for matching body hash / high similarity.
	5.	Fuzzy structural match
	•	Run subtree similarity only against a small candidate set (e.g., same kind, similar size, similar signature).
	6.	Confidence & classification
	•	If matched with high confidence but name/path changed → location change (update subscription).
	•	If body hash changed → content change (trigger).
	•	If signature hash changed → structural change (trigger).
	•	If only formatting/doc hash changed → cosmetic (likely no trigger).

⸻

3) Diff-based vs snapshot-based semantic analysis

Option A: Diff-based semantic analysis (parse only hunks / semantic diff)

Description
Try to interpret a git diff at AST/CST level: map hunks to syntax nodes and compute semantic edits.

Pros
	•	✓ Potentially very fast if you can avoid parsing full files.
	•	✓ Maps nicely to “what changed in this commit.”

Cons
	•	✗ Hard to do robustly: hunks may not parse standalone.
	•	✗ Move/rename refactorings are difficult without global context.
	•	✗ Handling partial/invalid code becomes messy.

Recommendation
Not my first pick for your tool. It’s a good future optimization once you already have a reliable snapshot-based approach.

⸻

Option B: Snapshot-based semantic analysis (parse old & new versions and compare)

Description
Parse file contents at commit^ and commit, extract construct index for each, then match and compute deltas.

Pros
	•	✓ Much simpler and more correct (full context is available).
	•	✓ Naturally supports moves/renames (because you can search entire new snapshot).
	•	✓ Works well with tolerant parsers (Tree-sitter).

Cons
	•	✗ Requires parsing two versions (but you can restrict to changed files).
	•	✗ Needs a matching strategy (the “identity problem”).

Recommendation (your use case)
Use snapshot-based as the core, and use git diff for:
	•	change scope,
	•	file rename detection (-M),  ￼
	•	and as a UX aid (“this moved from here to there”).

⸻

Tools for semantic/syntax-aware diffs (to learn from or integrate)

GumTree

Description: syntax-aware diff that aligns edits to syntax and can detect moved/renamed elements.  ￼
This is a classic AST differencing approach (Falleri et al., ASE 2014).

Pros
	•	✓ Explicitly tries to detect moves/renames in trees.  ￼
	•	✓ Can generate edit scripts (Insert/Delete/Update/Move).

Cons
	•	✗ Integration depends on having ASTs in a compatible format for each language.
	•	✗ Full mapping/edit script may be more than you need for subscriptions.

Use it if you want “refactoring-aware” explanations, or very detailed change classification.

⸻

difftastic

Description: “structural diff tool that compares files based on their syntax.”  ￼
Built on parsing (Tree-sitter ecosystem).

Pros
	•	✓ Great mental model / UX for syntax-aware diffs.
	•	✓ Many languages.

Cons
	•	✗ Primarily a CLI diff tool, not a construct tracker API.

Use it if you want a best-in-class display of semantic-ish diffs (or inspiration).

⸻

diffsitter

Description: Tree-sitter-based AST difftool.  ￼

Pros
	•	✓ Uses Tree-sitter as parser.
	•	✓ Focuses on meaningful diffs.

Cons
	•	✗ Again, mostly a tool, not a turnkey library for subscription mapping.

⸻

SemanticDiff (product/tool)

Description: language-aware diffs; hides irrelevant changes, detects moved code, highlights refactorings.  ￼

Pros
	•	✓ Strong behavior goals aligned with your “cosmetic vs real” classification.

Cons
	•	✗ Not necessarily a library you can embed.

⸻

4) Existing tools and libraries

Python-focused libraries

ast (stdlib)
	•	Best for high-precision extraction when code parses.  ￼

LibCST

What it is: a “lossless CST that looks and feels like an AST,” preserving formatting details and useful for codemods/linters.  ￼
Caveat: it will raise ParserSyntaxError when it can’t parse a piece of code.  ￼

When to use:
	•	if you want robust classification of “cosmetic-only” changes, or
	•	if you want to normalize formatting deterministically.

Parso

What it is: a Python parser with error recovery and round-trip parsing; “battle-tested by jedi.”  ￼

When to use:
	•	as a Python-specific tolerant parser (alternative/fallback to Tree-sitter),
	•	especially if you want Python-version-aware parsing with recovery.

Jedi

What it is: Python static analysis used in editors; focuses on autocompletion and “goto” functionality.  ￼
When to use:
	•	if you need name resolution (what does this identifier refer to?) without running code.

Rope

What it is: Python refactoring library (rename/move/etc). Rope documents rename/move refactorings.  ￼
When to use:
	•	if you want to apply refactorings or leverage refactoring logic as hints for matching.

Astroid

What it is: AST + inference support (powers pylint).  ￼
When to use:
	•	if you need “best effort” inference like attributes and some name meaning.

tokenize (stdlib)

What it is: Python lexical scanner that returns comments as tokens.  ￼
When to use:
	•	to build format-insensitive hashing, ignore comments, or track doc/comment deltas separately.

⸻

Language-agnostic tools

Tree-sitter (core parsing layer)

Best cross-language parsing foundation, robust to syntax errors.  ￼

Universal Ctags

What it provides: fast symbol indexing across many languages; supports JSON output (JSON Lines) when built with the right dependency.  ￼
When to use:
	•	cheap “symbol inventory” / coarse indexing layer,
	•	fallback when you don’t have a parser for a language yet.

LSP + LSIF + SCIP
	•	LSP: standardized way to query language intelligence (symbols, definitions, references).  ￼
	•	LSIF: persisted LSP-like knowledge for offline use.  ￼
	•	SCIP: language-agnostic indexing protocol (Sourcegraph).  ￼
	•	scip-python can generate stable references to dependencies; the format’s “symbol value” is explicitly a stable identifier string for code intelligence.  ￼

When to use:
	•	when you want “real” semantic identity: references/definitions, cross-file linking, and refactoring-grade accuracy.
	•	trade-off: indexers often need build/type environments.

⸻

5) Cross-language strategy (Python now → Java/Go later)

A good abstraction is a two-level interface:

Level 1: Parsing + extraction (syntax-level)

Goal: get constructs with ranges + hierarchy for any language.

Interface
	•	parse(file_content) -> syntax_tree
	•	extract_constructs(syntax_tree) -> [Construct]

Construct schema (language-neutral)
	•	kind: class | function | method | variable | field | import | etc.
	•	name
	•	container: parent construct ID (module/class)
	•	qualname (best-effort)
	•	range: (start_byte, end_byte, start_line, end_line)
	•	signature_features: params count, decorators/modifiers, annotations/types when available
	•	hashes:
	•	interface_hash
	•	body_hash_format_insensitive
	•	body_hash_alpha_normalized (optional)
	•	doc_hash (optional)
	•	parse_quality: OK | HAS_ERRORS | PARTIAL (important for tolerant parsing)

Implementation suggestion
	•	Use Tree-sitter for the parse tree and per-language query files to extract constructs. Tree-sitter is designed to be general and robust to syntax errors.  ￼

Level 2: Optional semantic enrichment (name resolution)

Goal: make identity/refactoring detection more reliable.

Pluggable enrichers:
	•	lsp_enricher: asks a language server for symbol IDs, references, etc.  ￼
	•	scip_enricher: consumes SCIP/LSIF indexes if available.  ￼

You can keep your system fully functional without Level 2, and enable it per repo/language when performance/environment allows.

⸻

Concrete recommendations per approach (as you requested)

Parsing approach recommendations

Native AST (ast)
	•	Use when: file parses cleanly and you want maximum Python semantic accuracy.
	•	Avoid as sole parser: because you must tolerate broken code.
	•	My take: “nice-to-have precision layer,” not the foundation.  ￼

Tree-sitter
	•	Use when: you need tolerant parsing + cross-language expansion.
	•	My take: should be your primary parse layer.  ￼

LSP
	•	Use when: you need refactoring-grade identity (rename references), cross-file linking.
	•	My take: optional “power mode,” not required for the POC.  ￼

Regex
	•	Use when: fallback-only; emergency extraction when parsing fails.
	•	My take: don’t base construct identity on it.

⸻

A pragmatic MVP plan (Python-first, extensible)
	1.	Changed file discovery
	•	Use git diff -M --name-status <old> <new> to detect changed files + renames.  ￼
	2.	Parse snapshots
	•	Parse old and new content with Tree-sitter Python grammar.  ￼
	•	Record parse_quality based on presence of error nodes.
	3.	Extract constructs
	•	Query for: class defs, function defs, decorators, parameter lists, assignments at module/class scope.
	•	Store range and the minimal hierarchy.
	4.	Compute fingerprints
	•	interface_hash: kind + (params/decorators/modifiers) excluding name.
	•	body_hash: normalized tokens excluding whitespace/comments (Python tokenize can help).  ￼
	•	doc_hash: separate.
	5.	Match constructs
	•	Exact (FQN + full signature)
	•	Rename-resistant (parent + interface_hash + high body similarity)
	•	Move detection (search across renamed/changed files)
	•	Fuzzy match only for unresolved subscriptions
	6.	Classify and act
	•	Only range/path changed → update subscription target, no trigger.
	•	interface_hash changed → structural trigger.
	•	body_hash changed → content trigger.
	•	only doc_hash or formatting changed → cosmetic (usually no action).

⸻

If you want, I can also sketch a minimal data model + matching pseudocode (with the exact fields/hashes I’d store) and an extraction strategy for Python constructs that cleanly maps to Tree-sitter queries—so you can implement the POC quickly and keep it compatible with Java/Go extractors later.
