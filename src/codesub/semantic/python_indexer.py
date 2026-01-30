"""Python construct extraction using Tree-sitter."""

from __future__ import annotations

import re

import tree_sitter
import tree_sitter_python as tspython

from .construct import Construct
from .fingerprint import compute_body_hash, compute_interface_hash


class PythonIndexer:
    """Extracts constructs from Python source code."""

    def __init__(self) -> None:
        self._language = tree_sitter.Language(tspython.language())
        self._parser = tree_sitter.Parser(self._language)

    def index_file(self, source: str, path: str) -> list[Construct]:
        """Extract all constructs from source code."""
        tree = self._parser.parse(source.encode())
        has_errors = self._has_errors(tree.root_node)
        constructs: list[Construct] = []

        source_bytes = source.encode()

        # Extract module-level assignments (variables/constants)
        constructs.extend(
            self._extract_module_assignments(tree.root_node, source_bytes, path, has_errors)
        )

        # Extract classes with their fields and methods
        constructs.extend(
            self._extract_classes(tree.root_node, source_bytes, path, has_errors)
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
        """Check if tree contains ERROR nodes."""
        if node.type == "ERROR":
            return True
        return any(self._has_errors(child) for child in node.children)

    def _extract_module_assignments(
        self,
        root: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
    ) -> list[Construct]:
        """Extract module-level variable/constant assignments."""
        constructs: list[Construct] = []

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

        return constructs

    def _extract_classes(
        self,
        root: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        has_errors: bool,
    ) -> list[Construct]:
        """Extract classes with their fields and methods."""
        constructs: list[Construct] = []

        for child in root.children:
            # Handle both plain class_definition and decorated classes
            class_node = None
            decorated_node = None
            if child.type == "class_definition":
                class_node = child
            elif child.type == "decorated_definition":
                decorated_node = child
                # Find the class_definition inside the decorated_definition
                for inner in child.children:
                    if inner.type == "class_definition":
                        class_node = inner
                        break

            if class_node is None:
                continue

            class_name = self._get_name(class_node)
            if not class_name:
                continue

            # Get class body
            body = class_node.child_by_field_name("body")
            if not body:
                continue

            # Emit container construct for the class itself
            container_construct = self._parse_class_container(
                class_node, source_bytes, path, has_errors, decorated_node
            )
            if container_construct:
                constructs.append(container_construct)

            # Extract class members
            constructs.extend(
                self._extract_class_members(
                    body, source_bytes, path, class_name, has_errors
                )
            )

        return constructs

    def _extract_class_members(
        self,
        body: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        class_name: str,
        has_errors: bool,
    ) -> list[Construct]:
        """Extract members (fields, methods, nested classes) from a class body."""
        constructs: list[Construct] = []

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

            # Method: def name(...): ...
            elif member.type == "function_definition":
                construct = self._parse_method(
                    member, source_bytes, path, class_name, has_errors
                )
                if construct:
                    constructs.append(construct)

            # Decorated method or nested class
            elif member.type == "decorated_definition":
                func = None
                nested_class = None
                for c in member.children:
                    if c.type == "function_definition":
                        func = c
                        break
                    elif c.type == "class_definition":
                        nested_class = c
                        break

                if func:
                    construct = self._parse_method(
                        func,
                        source_bytes,
                        path,
                        class_name,
                        has_errors,
                        decorated_node=member,
                    )
                    if construct:
                        constructs.append(construct)
                elif nested_class:
                    # Decorated nested class
                    nested_construct = self._parse_class_container(
                        nested_class,
                        source_bytes,
                        path,
                        has_errors,
                        decorated_node=member,
                        parent_qualname=class_name,
                    )
                    if nested_construct:
                        constructs.append(nested_construct)

            # Plain nested class
            elif member.type == "class_definition":
                nested_construct = self._parse_class_container(
                    member,
                    source_bytes,
                    path,
                    has_errors,
                    decorated_node=None,
                    parent_qualname=class_name,
                )
                if nested_construct:
                    constructs.append(nested_construct)

        return constructs

    def _parse_assignment(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        class_name: str | None,
        has_errors: bool,
    ) -> Construct | None:
        """Parse: NAME = value  OR  NAME: type = value  OR  NAME: type"""
        # In tree-sitter-python 0.25+, type annotations are children of assignment nodes
        # Structure: assignment { identifier, ":", type, "=", value }
        # Or: assignment { identifier, ":", type } (annotation without value)
        # Or: assignment { identifier, "=", value } (plain assignment)

        # Find the identifier (first child that's an identifier)
        name_node = None
        type_node = None
        value_node = None

        for child in node.children:
            if child.type == "identifier" and name_node is None:
                name_node = child
            elif child.type == "type":
                type_node = child

        # Try field-based access for left/right (works for plain assignments)
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        # Use field-based name if available, otherwise use first identifier
        if left and left.type == "identifier":
            name_node = left
        if right:
            value_node = right

        # For annotated assignments, the value might be the last non-punctuation child
        if value_node is None and type_node is not None:
            # Find value after the "=" sign
            found_equals = False
            for child in node.children:
                if child.type == "=":
                    found_equals = True
                elif found_equals and child.type not in (":", "=", "type"):
                    value_node = child
                    break

        if not name_node or name_node.type != "identifier":
            return None

        name = self._node_text(name_node, source_bytes)
        qualname = f"{class_name}.{name}" if class_name else name
        kind = "field" if class_name else "variable"
        role = "const" if self._is_constant_name(name) else None

        # interface_hash: includes type annotation if present
        annotation = None
        if type_node:
            annotation = self._node_text(type_node, source_bytes)
        interface_hash = compute_interface_hash(kind, annotation=annotation, decorators=[])

        # body_hash: the RHS value (or "<no-default>" if no value)
        if value_node:
            body_hash = compute_body_hash(value_node, source_bytes)
        else:
            body_hash = compute_body_hash(None, source_bytes)

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

    def _parse_method(
        self,
        node: tree_sitter.Node,
        source_bytes: bytes,
        path: str,
        class_name: str,
        has_errors: bool,
        decorated_node: tree_sitter.Node | None = None,
    ) -> Construct | None:
        """Parse method definition."""
        name = self._get_name(node)
        if not name:
            return None

        qualname = f"{class_name}.{name}"

        # Get decorators
        decorators: list[str] = []
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

    def _get_name(self, node: tree_sitter.Node) -> str | None:
        """Get name from class/function definition."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return name_node.text.decode() if name_node.text else None
        return None

    def _node_text(self, node: tree_sitter.Node, source_bytes: bytes) -> str:
        """Get text content of a node."""
        return source_bytes[node.start_byte : node.end_byte].decode()

    def _is_constant_name(self, name: str) -> bool:
        """Check if name follows CONSTANT_CASE convention."""
        return bool(re.match(r"^[A-Z][A-Z0-9_]*$", name))

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
