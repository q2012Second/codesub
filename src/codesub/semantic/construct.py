"""Construct dataclass for semantic code analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Construct:
    """A parsed code construct.

    Represents a semantic unit extracted from source code, such as a
    class, method, field, or variable. Used for semantic subscriptions
    that track code by identity rather than line numbers.

    Attributes:
        path: File path where the construct is defined.
        kind: Type of construct. Valid values:
            - "variable": Module-level variable
            - "field": Class field or attribute
            - "method": Method or function within a class
            - "class": Class declaration
            - "interface": Interface declaration (Java)
            - "enum": Enum declaration
        qualname: Qualified name of the construct.
            - Simple: "MAX_RETRIES", "User"
            - Nested: "User.role", "Calculator.add(int,int)"
            - Java overloads include param types: "add(int,int)"
        role: Optional role modifier.
            - "const": For constants (UPPER_CASE naming)
            - None: For regular constructs
        start_line: 1-based start line number (includes decorators if present).
        end_line: 1-based end line number (inclusive).
        definition_line: 1-based line of the actual definition (class/def keyword).
            For decorated constructs, this differs from start_line.
        interface_hash: Hash of the construct's interface/signature.
            Changes indicate structural changes (type annotations, parameters).
        body_hash: Hash of the construct's body/value.
            Changes indicate content changes (implementation, value).
        has_parse_error: True if the file had parse errors.
    """

    path: str
    kind: str  # "variable"|"field"|"method"|"class"|"interface"|"enum"
    qualname: str  # "MAX_RETRIES" | "User.role" | "Calculator.add(int,int)"
    role: str | None  # "const" for constants
    start_line: int
    end_line: int
    definition_line: int  # Line of actual class/def keyword (differs from start_line if decorated)
    interface_hash: str
    body_hash: str
    has_parse_error: bool = False
