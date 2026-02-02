"""Java construct extraction using Tree-sitter."""

from __future__ import annotations

import tree_sitter
import tree_sitter_java as tsjava

from .construct import Construct
from .fingerprint import compute_body_hash, compute_interface_hash


class JavaIndexer:
    """Extracts constructs from Java source code.

    Supports:
    - Type declarations: class, interface, enum
    - Fields (including multi-declarator: int x, y;)
    - Methods with overload-safe qualnames: Calculator.add(int,int)
    - Constructors: User.User(String)
    - Enum constants as field with role="const"
    - Nested classes: Outer.Inner.method()
    - Annotations affect interface_hash
    """

    def __init__(self) -> None:
        self._language = tree_sitter.Language(tsjava.language())
        self._parser = tree_sitter.Parser(self._language)

    def index_file(self, source: str, path: str) -> list[Construct]:
        """Extract all constructs from source code."""
        tree = self._parser.parse(source.encode())
        has_errors = self._has_errors(tree.root_node)
        source_bytes = source.encode()

        constructs: list[Construct] = []

        # Process top-level declarations
        for child in tree.root_node.children:
            constructs.extend(
                self._extract_declaration(child, source_bytes, path, has_errors, [])
            )

        return constructs

    def find_construct(
        self, source: str, path: str, qualname: str, kind: str | None = None
    ) -> Construct | None:
        """Find a specific construct by qualname."""
        constructs = self.index_file(source, path)
        matches = [c for c in constructs if c.qualname == qualname]
        if kind:
            matches = [c for c in matches if c.kind == kind]
        return matches[0] if len(matches) == 1 else None

    def _has_errors(self, node: tree_sitter.Node) -> bool:
        """Check if tree contains ERROR or MISSING nodes."""
        if node.type == "ERROR" or node.is_missing:
            return True
        return any(self._has_errors(child) for child in node.children)

    def _extract_declaration(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> list[Construct]:
        """Extract constructs from a declaration node."""
        constructs: list[Construct] = []

        if node.type == "class_declaration":
            constructs.extend(
                self._extract_class(node, source_bytes, path, has_errors, scope, "class")
            )
        elif node.type == "interface_declaration":
            constructs.extend(
                self._extract_class(node, source_bytes, path, has_errors, scope, "interface")
            )
        elif node.type == "enum_declaration":
            constructs.extend(
                self._extract_enum(node, source_bytes, path, has_errors, scope)
            )
        elif node.type == "field_declaration":
            constructs.extend(
                self._extract_field(node, source_bytes, path, has_errors, scope)
            )
        elif node.type == "method_declaration":
            construct = self._extract_method(node, source_bytes, path, has_errors, scope)
            if construct:
                constructs.append(construct)
        elif node.type == "constructor_declaration":
            construct = self._extract_constructor(node, source_bytes, path, has_errors, scope)
            if construct:
                constructs.append(construct)

        return constructs

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

        # Extract base classes for inheritance tracking
        base_classes = self._extract_base_classes(superclass, interfaces, source_bytes)

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
                base_classes=base_classes if base_classes else None,
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

    def _extract_enum(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> list[Construct]:
        """Extract enum declaration and its constants."""
        constructs: list[Construct] = []

        name = self._get_name(node)
        if not name:
            return constructs

        qualname = ".".join(scope + [name])

        # Get decorators (annotations)
        decorators = self._get_annotations(node, source_bytes)
        modifiers = self._get_modifiers(node, source_bytes)

        # Get interfaces if enum implements any
        interfaces = node.child_by_field_name("interfaces")

        # Extract base classes for inheritance tracking (enums can implement interfaces)
        base_classes = self._extract_base_classes(None, interfaces, source_bytes)

        annotation_text = self._node_text(interfaces, source_bytes) if interfaces else None

        interface_hash = compute_interface_hash(
            "enum",
            annotation=annotation_text,
            decorators=modifiers + decorators,
        )
        body_hash = compute_body_hash(None, source_bytes)

        constructs.append(
            Construct(
                path=path,
                kind="enum",
                qualname=qualname,
                role=None,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                definition_line=node.start_point[0] + 1,
                interface_hash=interface_hash,
                body_hash=body_hash,
                has_parse_error=has_errors,
                base_classes=base_classes if base_classes else None,
            )
        )

        # Process enum body
        body = node.child_by_field_name("body")
        if body:
            new_scope = scope + [name]
            for child in body.children:
                if child.type == "enum_constant":
                    construct = self._extract_enum_constant(
                        child, source_bytes, path, has_errors, new_scope
                    )
                    if construct:
                        constructs.append(construct)
                else:
                    # Process other members (methods, fields)
                    constructs.extend(
                        self._extract_declaration(
                            child, source_bytes, path, has_errors, new_scope
                        )
                    )

        return constructs

    def _extract_enum_constant(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> Construct | None:
        """Extract an enum constant as a field with role='const'."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = self._node_text(name_node, source_bytes)
        qualname = ".".join(scope + [name])

        # Get annotations on the enum constant
        decorators = self._get_annotations(node, source_bytes)

        interface_hash = compute_interface_hash(
            "field",
            annotation=None,
            decorators=decorators,
        )

        # Body hash includes arguments if present
        arguments = node.child_by_field_name("arguments")
        body_hash = compute_body_hash(arguments, source_bytes)

        return Construct(
            path=path,
            kind="field",
            qualname=qualname,
            role="const",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            definition_line=node.start_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _extract_field(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> list[Construct]:
        """Extract field declarations, handling multi-declarator cases."""
        constructs: list[Construct] = []

        # Get type and modifiers
        type_node = node.child_by_field_name("type")
        type_text = self._node_text(type_node, source_bytes) if type_node else None

        decorators = self._get_annotations(node, source_bytes)
        modifiers = self._get_modifiers(node, source_bytes)

        # Check if it's a constant (static final)
        is_const = "static" in modifiers and "final" in modifiers

        # Find all declarators
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue

                name = self._node_text(name_node, source_bytes)
                qualname = ".".join(scope + [name])

                # Interface hash includes type and modifiers
                interface_hash = compute_interface_hash(
                    "field",
                    annotation=type_text,
                    decorators=modifiers + decorators,
                )

                # Body hash includes the initializer value
                value_node = child.child_by_field_name("value")
                body_hash = compute_body_hash(value_node, source_bytes)

                constructs.append(
                    Construct(
                        path=path,
                        kind="field",
                        qualname=qualname,
                        role="const" if is_const else None,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        definition_line=node.start_point[0] + 1,
                        interface_hash=interface_hash,
                        body_hash=body_hash,
                        has_parse_error=has_errors,
                    )
                )

        return constructs

    def _extract_method(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> Construct | None:
        """Extract method declaration with overload-safe qualname."""
        name = self._get_name(node)
        if not name:
            return None

        # Build qualname with parameter types for overload distinction
        params_node = node.child_by_field_name("parameters")
        param_types = self._extract_param_types(params_node, source_bytes)
        qualname = ".".join(scope + [f"{name}({','.join(param_types)})"])

        # Get return type
        return_type = node.child_by_field_name("type")
        return_text = self._node_text(return_type, source_bytes) if return_type else "void"

        # Get decorators and modifiers
        decorators = self._get_annotations(node, source_bytes)
        modifiers = self._get_modifiers(node, source_bytes)

        # Get throws clause
        throws = None
        for child in node.children:
            if child.type == "throws":
                throws = self._node_text(child, source_bytes)
                break

        annotation_parts = [return_text]
        if throws:
            annotation_parts.append(throws)

        interface_hash = compute_interface_hash(
            "method",
            annotation=" ".join(annotation_parts),
            decorators=modifiers + decorators,
            params_node=params_node,
            source_bytes=source_bytes,
        )

        # Body hash includes method body
        body_node = node.child_by_field_name("body")
        body_hash = compute_body_hash(body_node, source_bytes)

        return Construct(
            path=path,
            kind="method",
            qualname=qualname,
            role=None,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            definition_line=node.start_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _extract_constructor(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
        scope: list[str],
    ) -> Construct | None:
        """Extract constructor declaration."""
        name = self._get_name(node)
        if not name:
            return None

        # Build qualname with parameter types
        params_node = node.child_by_field_name("parameters")
        param_types = self._extract_param_types(params_node, source_bytes)
        qualname = ".".join(scope + [f"{name}({','.join(param_types)})"])

        # Get decorators and modifiers
        decorators = self._get_annotations(node, source_bytes)
        modifiers = self._get_modifiers(node, source_bytes)

        # Get throws clause
        throws = None
        for child in node.children:
            if child.type == "throws":
                throws = self._node_text(child, source_bytes)
                break

        interface_hash = compute_interface_hash(
            "method",
            annotation=throws,
            decorators=modifiers + decorators,
            params_node=params_node,
            source_bytes=source_bytes,
        )

        # Body hash includes constructor body
        body_node = node.child_by_field_name("body")
        body_hash = compute_body_hash(body_node, source_bytes)

        return Construct(
            path=path,
            kind="method",
            qualname=qualname,
            role=None,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            definition_line=node.start_point[0] + 1,
            interface_hash=interface_hash,
            body_hash=body_hash,
            has_parse_error=has_errors,
        )

    def _extract_param_types(
        self, params_node: tree_sitter.Node | None, source_bytes: bytes
    ) -> list[str]:
        """Extract parameter types for overload-safe qualnames."""
        if not params_node:
            return []

        types: list[str] = []
        for child in params_node.children:
            if child.type == "formal_parameter":
                type_node = child.child_by_field_name("type")
                if type_node:
                    type_text = self._node_text(type_node, source_bytes)
                    # Normalize arrays and generics
                    type_text = type_text.replace(" ", "")
                    types.append(type_text)
            elif child.type == "spread_parameter":
                # spread_parameter has type_identifier child, not "type" field
                type_text = None
                for subchild in child.children:
                    if subchild.type in ("type_identifier", "generic_type", "array_type"):
                        type_text = self._node_text(subchild, source_bytes)
                        break
                if type_text:
                    type_text = type_text.replace(" ", "") + "..."
                    types.append(type_text)

        return types

    def _get_annotations(
        self, node: tree_sitter.Node, source_bytes: bytes
    ) -> list[str]:
        """Get annotation decorators for a node."""
        annotations: list[str] = []

        # Look for annotations as direct children or inside modifiers node
        for child in node.children:
            if child.type in ("marker_annotation", "annotation"):
                annotations.append(self._node_text(child, source_bytes))
            elif child.type == "modifiers":
                # Java often puts annotations inside the modifiers node
                for mod in child.children:
                    if mod.type in ("marker_annotation", "annotation"):
                        annotations.append(self._node_text(mod, source_bytes))

        return annotations

    def _get_modifiers(
        self, node: tree_sitter.Node, source_bytes: bytes
    ) -> list[str]:
        """Get modifiers (public, static, final, etc.) for a node."""
        modifiers: list[str] = []

        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type not in ("marker_annotation", "annotation"):
                        text = self._node_text(mod, source_bytes)
                        if text:
                            modifiers.append(text)
        return modifiers

    def _get_name(self, node: tree_sitter.Node) -> str | None:
        """Get name from a declaration node."""
        name_node = node.child_by_field_name("name")
        if name_node and name_node.text:
            return name_node.text.decode()
        return None

    def _node_text(self, node: tree_sitter.Node, source_bytes: bytes) -> str:
        """Get text content of a node."""
        return source_bytes[node.start_byte:node.end_byte].decode()

    def _extract_base_classes(
        self,
        superclass_node: tree_sitter.Node | None,
        interfaces_node: tree_sitter.Node | None,
        source_bytes: bytes,
    ) -> tuple[str, ...]:
        """Extract base class/interface names from extends/implements.

        Java classes can extend one class and implement multiple interfaces.
        Returns all as a single tuple (extends first, then implements).

        Handles:
        - extends BaseClass
        - extends BaseClass<T>  (generic) -> "BaseClass"
        - implements Interface1, Interface2
        """
        base_names: list[str] = []

        # Handle extends (single class for classes, could be type_list for interfaces)
        if superclass_node:
            self._extract_type_names(superclass_node, source_bytes, base_names)

        # Handle implements (interface list)
        if interfaces_node:
            # interfaces node contains type_list with type_identifiers
            for child in interfaces_node.children:
                if child.type == "type_list":
                    for type_node in child.children:
                        self._extract_type_names(type_node, source_bytes, base_names)
                else:
                    self._extract_type_names(child, source_bytes, base_names)

        return tuple(base_names)

    def _extract_type_names(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        result: list[str],
    ) -> None:
        """Extract type name from a type node, stripping generics.

        Handles wrapper nodes (superclass, interfaces) by iterating through children.
        """
        if node.type == "type_identifier":
            result.append(self._node_text(node, source_bytes))
        elif node.type == "generic_type":
            # Generic: List<T> -> extract "List"
            for child in node.children:
                if child.type == "type_identifier":
                    result.append(self._node_text(child, source_bytes))
                    break
        elif node.type == "scoped_type_identifier":
            # Qualified: com.example.User -> extract full path
            result.append(self._node_text(node, source_bytes))
        elif node.type in ("superclass", "type_list"):
            # Wrapper nodes - iterate through children
            for child in node.children:
                self._extract_type_names(child, source_bytes, result)

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

    def extract_imports(self, source: str) -> dict[str, tuple[str, str]]:
        """Extract import mappings from Java source using Tree-sitter.

        Returns dict mapping simple class name to (full_import_path, simple_name).
        Example: {"User": ("com.example.models.User", "User")}

        Handles:
        - import com.example.User;
        - Skips: import com.example.*; (wildcard - cannot resolve)
        - Skips: import static com.example.Utils.helper; (static imports)
        """
        tree = self._parser.parse(source.encode())
        source_bytes = source.encode()
        import_map: dict[str, tuple[str, str]] = {}

        for child in tree.root_node.children:
            if child.type == "import_declaration":
                # Check for static import or wildcard
                is_static = False
                is_wildcard = False

                for part in child.children:
                    if part.type == "static":
                        is_static = True
                    elif part.type == "asterisk":
                        is_wildcard = True

                # Skip static and wildcard imports
                if is_static or is_wildcard:
                    continue

                # Find the scoped_identifier (full path)
                for part in child.children:
                    if part.type == "scoped_identifier":
                        full_path = self._node_text(part, source_bytes)
                        simple_name = full_path.split(".")[-1]
                        import_map[simple_name] = (full_path, simple_name)
                        break
                    elif part.type == "identifier":
                        # Single identifier import (rare but possible)
                        name = self._node_text(part, source_bytes)
                        import_map[name] = (name, name)

        return import_map
