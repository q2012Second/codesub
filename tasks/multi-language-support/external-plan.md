Implementation Plan: Multi-Language Semantic Indexing

Overview

Introduce a language-agnostic semantic indexing layer built around a small Protocol interface and a registry/factory that selects an indexer by file extension (auto-detection). Keep existing fingerprinting and Construct shape intact, add a new JavaIndexer (Tree-sitter Java), and replace the 4 hardcoded PythonIndexer() instantiations with the factory.

Key outcomes:
	•	Python continues to work unchanged (same hashes, same stored "python" language values).
	•	Java gains semantic subscriptions for:
	•	class, interface, enum declarations
	•	field declarations (including multi-declarator statements)
	•	method declarations (including constructors)
	•	Unsupported languages fail with a clear UnsupportedLanguageError (CLI + API), and scanning can degrade gracefully.

⸻

Prerequisites
	•	Add tree-sitter-java dependency (so tree_sitter_java.language() is available).
	•	Decide/standardize Java qualname conventions (recommended below):
	•	Types: Outer.Inner
	•	Fields: Outer.Inner.FIELD
	•	Methods: Outer.Inner.method(Type1,Type2)
	•	Constructors: Outer.Inner.Inner(Type1,Type2) (matches your “ClassName.ClassName” suggestion, disambiguates overloads)

⸻

Implementation Steps

Step 1: Add Tree-sitter Java dependency

File: pyproject.toml
Changes:
	•	Add the dependency alongside tree-sitter-python.

[tool.poetry.dependencies]
tree-sitter = ">=0.21.0"
tree-sitter-python = ">=0.21.0"
tree-sitter-java = ">=0.21.0"

Notes:
	•	Keep version ranges aligned with the existing tree-sitter-* deps to reduce ABI mismatches.

⸻

Step 2: Make Construct explicitly language-agnostic

Goal: JavaIndexer shouldn’t need to import from python_indexer.py.

File: src/codesub/semantic/construct.py (new)
Changes:
	•	Move the current Construct dataclass verbatim into this module (do not change fields).

# src/codesub/semantic/construct.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Construct:
    path: str
    kind: str
    qualname: str
    role: str | None
    start_line: int
    end_line: int
    interface_hash: str
    body_hash: str
    has_parse_error: bool = False

File: src/codesub/semantic/python_indexer.py
Changes:
	•	Remove the Construct definition and import it from .construct.

from .construct import Construct

Backward compatibility:
	•	codesub.semantic.Construct will remain available via exports in Step 7.

⸻

Step 3: Define the indexer Protocol

File: src/codesub/semantic/indexer_protocol.py (new)
Changes:
	•	Define a minimal protocol matching existing PythonIndexer usage patterns.

from __future__ import annotations
from typing import Protocol
from .construct import Construct

class SemanticIndexer(Protocol):
    def index_file(self, source: str, path: str) -> list[Construct]:
        ...

    def find_construct(
        self, source: str, path: str, qualname: str, kind: str | None = None
    ) -> Construct | None:
        ...

Why minimal:
	•	Keeps refactors small (you already depend only on these two methods in CLI/Detector/API).

⸻

Step 4: Add a registry + language auto-detection factory

File: src/codesub/semantic/registry.py (new)
Changes:
	•	Implement:
	•	register_indexer(language, extensions, factory)
	•	detect_language(path)
	•	get_indexer(language)
	•	get_indexer_for_path(path, language=None) (returns (language, indexer))

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .indexer_protocol import SemanticIndexer
from ..errors import UnsupportedLanguageError

IndexerFactory = Callable[[], SemanticIndexer]

_REGISTRY: dict[str, IndexerFactory] = {}
_EXT_TO_LANG: dict[str, str] = {}

def register_indexer(language: str, extensions: list[str], factory: IndexerFactory) -> None:
    _REGISTRY[language] = factory
    for ext in extensions:
        _EXT_TO_LANG[ext.lower()] = language

def supported_languages() -> list[str]:
    return sorted(_REGISTRY.keys())

def detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    lang = _EXT_TO_LANG.get(ext)
    if not lang:
        raise UnsupportedLanguageError(
            language=ext or "<no-extension>",
            supported=supported_languages(),
            hint="Semantic subscriptions require a supported file extension.",
        )
    return lang

def get_indexer(language: str) -> SemanticIndexer:
    factory = _REGISTRY.get(language)
    if not factory:
        raise UnsupportedLanguageError(
            language=language,
            supported=supported_languages(),
            hint="Use a supported language or add an indexer via register_indexer().",
        )
    return factory()

def get_indexer_for_path(path: str, language: str | None = None) -> tuple[str, SemanticIndexer]:
    lang = language or detect_language(path)
    return lang, get_indexer(lang)


⸻

Step 5: Add UnsupportedLanguageError

File: src/codesub/errors.py
Changes:
	•	Add a new error class.

class UnsupportedLanguageError(CodesubError):
    """Raised when semantic indexing is requested for an unsupported language."""

    def __init__(self, language: str, supported: list[str], hint: str | None = None):
        self.language = language
        self.supported = supported
        msg = f"Unsupported language '{language}'. Supported: {', '.join(supported) or '<none>'}."
        if hint:
            msg = f"{msg} {hint}"
        super().__init__(msg)

Behavior expectations:
	•	CLI: prints Error: Unsupported language ...
	•	API: automatically mapped by CodesubError handler (you may optionally add to ERROR_STATUS_CODES as 400).

⸻

Step 6: Implement JavaIndexer

File: src/codesub/semantic/java_indexer.py (new)
Approach: Mirror PythonIndexer structure:
	•	__init__: set Tree-sitter language and parser
	•	index_file: parse, compute has_errors, extract constructs
	•	find_construct: same semantics
	•	Internal helpers: _has_errors, _node_text, _get_name, plus extractors for types/fields/methods

6.1: Skeleton + parse plumbing

import tree_sitter
import tree_sitter_java as tsjava

from .construct import Construct
from .fingerprint import compute_body_hash, compute_interface_hash

class JavaIndexer:
    """Extracts constructs from Java source code."""

    def __init__(self) -> None:
        self._language = tree_sitter.Language(tsjava.language())
        self._parser = tree_sitter.Parser(self._language)

    def index_file(self, source: str, path: str) -> list[Construct]:
        tree = self._parser.parse(source.encode())
        has_errors = self._has_errors(tree.root_node)
        source_bytes = source.encode()

        constructs: list[Construct] = []
        constructs.extend(self._extract_types(tree.root_node, source_bytes, path, has_errors, scope=[]))
        return constructs

    def find_construct(self, source: str, path: str, qualname: str, kind: str | None = None) -> Construct | None:
        constructs = self.index_file(source, path)
        matches = [c for c in constructs if c.qualname == qualname]
        if kind:
            matches = [c for c in matches if c.kind == kind]
        return matches[0] if len(matches) == 1 else None

    def _has_errors(self, node: tree_sitter.Node) -> bool:
        if node.type == "ERROR":
            return True
        return any(self._has_errors(child) for child in node.children)

6.2: Recursive type extraction (handles nested/inner classes)
Key requirements addressed:
	•	Nested/inner classes: Outer.Inner.method(...)
	•	Type kinds: class, interface, enum

def _extract_types(self, node, source_bytes, path, has_errors, scope: list[str]) -> list[Construct]:
    constructs: list[Construct] = []

    for child in node.children:
        decl = self._unwrap_decl(child)  # handles wrappers like class_body_declaration
        if decl is None:
            continue

        if decl.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            constructs.extend(self._parse_type_decl(decl, source_bytes, path, has_errors, scope))
        else:
            # also traverse to catch top-level types nested in other nodes if grammar wraps them
            constructs.extend(self._extract_types(decl, source_bytes, path, has_errors, scope))

    return constructs

_parse_type_decl details:
	•	Determine kind based on node type: class / interface / enum
	•	Determine qualname: ".".join(scope + [name])
	•	Compute interface_hash:
	•	decorators: modifiers + annotations (normalized)
	•	annotation: normalized extends/implements clause (no name!)
	•	Compute body_hash from the body node (class_body / interface_body / enum_body)
	•	Recurse into body to extract members and nested types

def _parse_type_decl(...):
    name = self._get_name(decl)
    kind = {"class_declaration":"class", "interface_declaration":"interface", "enum_declaration":"enum"}[decl.type]
    qual = ".".join(scope + [name])

    decorators = self._extract_modifiers_and_annotations(decl, source_bytes)
    header = self._extract_type_header_signature(decl, source_bytes)  # extends/implements/type params
    interface_hash = compute_interface_hash(kind, annotation=header, decorators=decorators)

    body = decl.child_by_field_name("body")
    body_hash = compute_body_hash(body, source_bytes) if body else compute_body_hash(None, source_bytes)

    constructs.append(Construct(... kind=kind, qualname=qual, ...))

    # Parse members inside body, pass scope + [name]
    if body:
        constructs.extend(self._extract_members(body, source_bytes, path, has_errors, scope + [name]))

    return constructs

6.3: Member extraction (fields, methods, constructors, enum constants)
Members to support:
	•	field_declaration (including int x, y;)
	•	method_declaration
	•	constructor_declaration
	•	enum_constant list inside enums (as field with role "const")

Pseudo-outline:

def _extract_members(self, body, source_bytes, path, has_errors, scope: list[str]) -> list[Construct]:
    constructs: list[Construct] = []
    type_qual = ".".join(scope)

    for child in body.children:
        decl = self._unwrap_decl(child)
        if decl is None:
            continue

        if decl.type == "field_declaration":
            constructs.extend(self._parse_field_declaration(decl, source_bytes, path, type_qual, has_errors))
        elif decl.type == "method_declaration":
            c = self._parse_method_declaration(decl, source_bytes, path, type_qual, has_errors)
            if c: constructs.append(c)
        elif decl.type == "constructor_declaration":
            c = self._parse_constructor_declaration(decl, source_bytes, path, type_qual, scope[-1], has_errors)
            if c: constructs.append(c)
        elif decl.type in ("class_declaration","interface_declaration","enum_declaration"):
            constructs.extend(self._parse_type_decl(decl, source_bytes, path, has_errors, scope))
        elif decl.type == "enum_body":
            constructs.extend(self._parse_enum_constants(decl, source_bytes, path, type_qual, has_errors))
            constructs.extend(self._extract_members(decl, source_bytes, path, has_errors, scope))  # for enum body declarations

    return constructs

Field parsing: multi-declarator support
	•	For int x, y, z;, emit three Constructs:
	•	Type.x, Type.y, Type.z
	•	Use the same field type + modifiers for interface hash
	•	Body hash from each declarator’s initializer expression (or <no-default>)

def _parse_field_declaration(...):
    field_type = self._node_text(decl.child_by_field_name("type"), source_bytes)
    decorators = self._extract_modifiers_and_annotations(decl, source_bytes)
    interface_hash = compute_interface_hash("field", annotation=field_type, decorators=decorators)

    # variable_declarator nodes contain name + optional initializer
    for vd in self._find_children(decl, "variable_declarator"):
        name_node = vd.child_by_field_name("name")
        init_node = vd.child_by_field_name("value")

        name = self._node_text(name_node, source_bytes)
        qualname = f"{type_qual}.{name}"

        role = "const" if self._is_java_constant(decl, scope=type_qual, name=name, source_bytes=source_bytes) else None
        body_hash = compute_body_hash(init_node, source_bytes) if init_node else compute_body_hash(None, source_bytes)

        constructs.append(Construct(... kind="field", qualname=qualname, role=role, ...))

Methods + overload handling
	•	To support overloads cleanly, encode parameter types into qualname:
	•	Calculator.add(int,int)
	•	Calculator.add(java.util.List<String>) (use source type text as printed by parser)

Recommended helper:
	•	_method_signature_suffix(params_node) returns "(T1,T2)" with whitespace normalized and param names removed.

def _parse_method_declaration(...):
    name = self._get_name(decl)
    params = decl.child_by_field_name("parameters")
    ret = decl.child_by_field_name("type")  # or "return_type" depending on grammar

    decorators = self._extract_modifiers_and_annotations(decl, source_bytes)
    interface_hash = compute_interface_hash(
        "method",
        annotation=self._node_text(ret, source_bytes) if ret else None,
        decorators=decorators,
        params_node=params,
        source_bytes=source_bytes,
    )

    body = decl.child_by_field_name("body")
    body_hash = compute_body_hash(body, source_bytes) if body else compute_body_hash(None, source_bytes)

    sig = self._signature_suffix(params, source_bytes)  # "(int,int)" / "()"
    qualname = f"{type_qual}.{name}{sig}"

    return Construct(... kind="method", qualname=qualname, ...)

Constructors
	•	Kind: "method"
	•	Qualname: "{TypeQual}.{SimpleClassName}{sig}", e.g. User.User(int)
	•	Interface hash: same as methods, but annotation=None (no return type)

def _parse_constructor_declaration(..., class_simple_name: str, ...):
    params = decl.child_by_field_name("parameters")
    decorators = self._extract_modifiers_and_annotations(decl, source_bytes)

    interface_hash = compute_interface_hash(
        "method",
        annotation=None,
        decorators=decorators,
        params_node=params,
        source_bytes=source_bytes,
    )
    ...
    qualname = f"{type_qual}.{class_simple_name}{sig}"

Enum constants
	•	Treat enum constants as kind="field", role="const", qualname Enum.RED
	•	Body hash from arguments / class body of the constant (if present), else <no-default>

⸻

Step 7: Update fingerprint parameter normalization for Java

File: src/codesub/semantic/fingerprint.py
Changes:
	•	Extend _normalize_params to recognize Java parameter node types.
	•	Crucially: exclude Java parameter names (so renaming a parameter doesn’t change interface hash).

Implementation idea (minimal and safe for Python):
	•	Keep existing Python handling untouched.
	•	Add branch for Java nodes formal_parameter and spread_parameter:
	•	Find name field, slice everything before it.

def _normalize_params(params_node: "tree_sitter.Node", source_bytes: bytes) -> str:
    parts = []
    for child in params_node.children:
        if child.type in (...existing python types...):
            ...
        elif child.type in ("formal_parameter", "spread_parameter"):
            name_node = child.child_by_field_name("name")
            if name_node:
                text = source_bytes[child.start_byte : name_node.start_byte].decode()
            else:
                text = source_bytes[child.start_byte : child.end_byte].decode()
            text = " ".join(text.split())
            parts.append(text)
    return ",".join(parts)

Why this works:
	•	Keeps type annotations, varargs ..., parameter annotations like @Nullable, and modifiers like final
	•	Drops the trailing identifier parameter name (so int a vs int b hashes the same)

⸻

Step 8: Export registry + new indexer in semantic package

File: src/codesub/semantic/__init__.py
Changes:
	•	Export:
	•	Construct (from .construct)
	•	PythonIndexer (existing)
	•	JavaIndexer (new)
	•	Registry functions (detect_language, get_indexer, get_indexer_for_path, etc.)
	•	Register built-in languages on import.

from .construct import Construct
from .python_indexer import PythonIndexer
from .java_indexer import JavaIndexer
from .registry import register_indexer, detect_language, get_indexer, get_indexer_for_path

register_indexer("python", [".py"], PythonIndexer)
register_indexer("java", [".java"], JavaIndexer)

__all__ = [
    "Construct",
    "PythonIndexer",
    "JavaIndexer",
    "detect_language",
    "get_indexer",
    "get_indexer_for_path",
    ...
]

Backward compatibility:
	•	Existing imports still work: from codesub.semantic import PythonIndexer, Construct.

⸻

Step 9: Replace hardcoded PythonIndexer() usage with the factory

This is the core refactor that makes multi-language real.

9.1 CLI add semantic subscription
File: src/codesub/cli.py
Function: _add_semantic_subscription(...)
Changes:
	•	Replace PythonIndexer() with get_indexer_for_path(target.path)
	•	Set SemanticTarget.language to detected language
	•	Improve error message for unsupported languages

from .semantic import get_indexer_for_path
...
language, indexer = get_indexer_for_path(target.path)
...
semantic = SemanticTarget(
    language=language,
    kind=construct.kind,
    qualname=construct.qualname,
    role=construct.role,
    interface_hash=construct.interface_hash,
    body_hash=construct.body_hash,
)

9.2 CLI symbols command
File: src/codesub/cli.py
Function: cmd_symbols(args)
Changes:
	•	Use get_indexer_for_path(args.path)

Also update --kind choices to include Java kinds (see Step 10).

9.3 API subscription creation
File: src/codesub/api.py
Function: _create_subscription_from_request(...)
Changes:
	•	Use get_indexer_for_path(target.path) and store detected language in SemanticTarget.

9.4 Detector semantic scan
File: src/codesub/detector.py
Function: _check_semantic(...)
Changes:
	•	Use get_indexer(sub.semantic.language) rather than always PythonIndexer()

Additionally:
	•	If unsupported language: return a semantic trigger (recommended) so scan completes.
	•	If parse errors: optionally return PARSE_ERROR trigger.

Example structure:

from .semantic import get_indexer
from .errors import UnsupportedLanguageError

try:
    indexer = get_indexer(sub.semantic.language)
except UnsupportedLanguageError as e:
    return (
        Trigger(
            subscription_id=sub.id,
            subscription=sub,
            path=sub.path,
            start_line=sub.start_line,
            end_line=sub.end_line,
            reasons=["unsupported_language"],
            matching_hunks=[],
            change_type="AMBIGUOUS",
            details={"error": str(e), "language": sub.semantic.language},
        ),
        None,
    )


⸻

Step 10: Update target parsing + CLI filtering to include Java kinds

10.1 Target parsing
File: src/codesub/utils.py
Function: parse_target_spec(spec)
Changes:
	•	Extend recognized kind prefixes:
	•	variable, field, method (existing)
	•	class, interface, enum (new)

if maybe_kind in ("variable", "field", "method", "class", "interface", "enum"):
    kind = maybe_kind
    qualname = maybe_qualname

10.2 CLI symbols --kind choices
File: src/codesub/cli.py
Function: create_parser()
Changes:
	•	Expand choices list:

choices=["variable", "field", "method", "class", "interface", "enum"]

This is backwards compatible (existing choices still valid).

⸻

Step 11: Handle semantic ambiguity + parse errors explicitly

File: src/codesub/detector.py
Function: _check_semantic(...), _find_by_hash(...)
Changes:
	•	Add an “ambiguous match” pathway:
	•	When stage 2 hash-based search yields multiple candidates, return a Trigger(change_type="AMBIGUOUS") with details (candidate qualnames).
	•	Add a “parse error” pathway:
	•	If old_construct or new_construct has has_parse_error=True, return Trigger(change_type="PARSE_ERROR").

Minimal, low-risk integration:
	•	Change _find_by_hash to optionally return:
	•	None
	•	a single Construct
	•	or a special marker list (or a tuple (match, candidates))

Example plan (least invasive):
	•	Keep _find_by_hash returning Construct | None
	•	Add _find_all_by_hash(...) -> list[Construct]
	•	In _check_semantic, if len(candidates) > 1, return ambiguous trigger.

⸻

Testing Strategy

Unit tests: Java indexing + parsing

File: tests/test_semantic.py (extend) or new tests/test_semantic_java.py
Add a TestJavaIndexer suite parallel to TestPythonIndexer.
	•	Class declaration extracted
	•	Source: public class User { }
	•	Expect construct: kind="class", qualname="User"
	•	Interface and enum extracted
	•	interface I { }, enum Color { RED, BLUE }
	•	Expect kind="interface", kind="enum"
	•	Nested/inner classes
	•	class Outer { class Inner { void f(){} } }
	•	Expect: Outer.Inner type and Outer.Inner.f() method
	•	Field extraction (single + multi-declarator)
	•	int x;
	•	int x, y, z;
	•	Expect 1 construct vs 3 constructs, qualnames Type.x, etc.
	•	Enum constants as fields
	•	enum Color { RED, BLUE }
	•	Expect Color.RED and Color.BLUE as kind="field", role="const"
	•	Method signatures include parameter types (overload-safe qualnames)
	•	int add(int a, int b) => Calculator.add(int,int)
	•	int add(String s) => Calculator.add(String)
	•	Constructor support
	•	class C { C(int x) {} }
	•	Expect C.C(int) as kind="method"
	•	Annotations affect interface hash
	•	Add/remove @Deprecated on method/field and assert interface_hash changes
	•	Parameter name changes do not affect interface hash
	•	add(int a) vs add(int b) => same interface_hash
	•	Generics + varargs stable
	•	f(List<String> xs) => signature includes List<String>
	•	f(String... xs) => signature includes String...
	•	Parse error flagging
	•	Provide invalid Java source and ensure constructs (if any) have has_parse_error=True

Integration tests: semantic detector for Java

File: tests/test_semantic_detector.py (extend)
Add a new fixture + class similar to the Python repo tests.
	•	No change detected (Java)
	•	Field initializer value change triggers CONTENT
	•	Field type change triggers STRUCTURAL
	•	Method body change triggers CONTENT
	•	Rename field produces proposal via hash matching
	•	Line shift produces proposal
	•	Deleted construct triggers MISSING
	•	Overloaded methods: changing other overload does not trigger
	•	Unsupported language subscription returns AMBIGUOUS (or CLI/API error depending on path)

Implementation hint:
	•	Create semantic_java_repo(tmp_path) that writes Config.java, commits it, then modifies between commits just like the Python tests.

⸻

Edge Cases
	•	Nested/inner classes (Outer.Inner.method)
	•	Handled by recursive traversal with a scope stack building qualnames.
	•	Overloaded methods
	•	Avoid ambiguity by emitting qualnames including normalized parameter type list:
	•	Type.m(int) vs Type.m(String)
	•	find_construct() remains unchanged and stays reliable.
	•	Multiple fields per declaration (int x, y, z;)
	•	Emit one Construct per declarator.
	•	Potential ambiguity for rename proposals if several fields share identical initializer + type (same hashes). If multiple hash matches exist, return AMBIGUOUS with candidate list.
	•	Annotations
	•	Treat as “decorators” in compute_interface_hash (include normalized @Annotation(...) strings).
	•	Access modifiers
	•	Include in interface hash (recommended): changing public ↔ private is structural.
	•	Generics
	•	Included naturally via parameter/type node text.
	•	Normalized whitespace ensures formatting changes don’t trigger.
	•	Constructors
	•	Represented as kind="method", qualname Type.Type(...) for consistency with your suggestion and overload disambiguation.
	•	Parse errors
	•	Indexers set has_parse_error=True when Tree-sitter contains ERROR nodes.
	•	Detector can return PARSE_ERROR trigger to avoid silent false negatives.
	•	Unsupported languages
	•	CLI/API: raise UnsupportedLanguageError with supported list.
	•	Detector: recommended to return AMBIGUOUS trigger per subscription so scans don’t crash.

⸻

Risks & Mitigations
	•	Risk: Tree-sitter Java node field names differ slightly from assumptions (e.g., return_type vs type, parameters vs formal_parameters).
Mitigation: Implement small helper functions with fallbacks:
	•	Try child_by_field_name("type"), fallback to child_by_field_name("return_type"), etc.
	•	Add focused unit tests for each construct type to catch mismatches early.
	•	Risk: Hash compatibility regression for Python (breaking existing subscriptions).
Mitigation: Ensure fingerprint._normalize_params changes are additive and do not affect Python node types; keep existing Python tests + the hard-coded integration hash test.
	•	Risk: Ambiguity in hash-based rename detection (multiple identical candidates).
Mitigation: Add explicit AMBIGUOUS trigger with candidates; optionally suggest users subscribe using --kind and/or more specific targets.
	•	Risk: Qualname format becomes “API surface” users rely on.
Mitigation: Document the Java qualname scheme (especially overload signatures) and keep it stable. If you later revise it, bump SemanticTarget.fingerprint_version and support both formats.

⸻

￼
