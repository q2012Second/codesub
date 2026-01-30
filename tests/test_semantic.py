"""Tests for semantic code analysis."""

import pytest

from codesub.semantic import Construct, PythonIndexer, compute_body_hash, compute_interface_hash
from codesub.utils import LineTarget, SemanticTargetSpec, parse_target_spec


class TestTargetParsing:
    """Tests for target specification parsing."""

    def test_line_target_single_line(self):
        result = parse_target_spec("path/to/file.py:42")
        assert isinstance(result, LineTarget)
        assert result.path == "path/to/file.py"
        assert result.start_line == 42
        assert result.end_line == 42

    def test_line_target_range(self):
        result = parse_target_spec("path/to/file.py:42-50")
        assert isinstance(result, LineTarget)
        assert result.path == "path/to/file.py"
        assert result.start_line == 42
        assert result.end_line == 50

    def test_semantic_target_simple(self):
        result = parse_target_spec("path/to/file.py::MAX_RETRIES")
        assert isinstance(result, SemanticTargetSpec)
        assert result.path == "path/to/file.py"
        assert result.qualname == "MAX_RETRIES"
        assert result.kind is None

    def test_semantic_target_qualified(self):
        result = parse_target_spec("path/to/file.py::User.role")
        assert isinstance(result, SemanticTargetSpec)
        assert result.path == "path/to/file.py"
        assert result.qualname == "User.role"
        assert result.kind is None

    def test_semantic_target_with_kind(self):
        result = parse_target_spec("path/to/file.py::field:User.role")
        assert isinstance(result, SemanticTargetSpec)
        assert result.path == "path/to/file.py"
        assert result.qualname == "User.role"
        assert result.kind == "field"

    def test_semantic_target_method_kind(self):
        result = parse_target_spec("path/to/file.py::method:User.save")
        assert isinstance(result, SemanticTargetSpec)
        assert result.path == "path/to/file.py"
        assert result.qualname == "User.save"
        assert result.kind == "method"


class TestPythonIndexer:
    """Tests for Python construct extraction."""

    def test_module_variable(self):
        indexer = PythonIndexer()
        source = "MAX_RETRIES = 5"
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "variable"
        assert c.qualname == "MAX_RETRIES"
        assert c.role == "const"
        assert c.start_line == 1
        assert c.end_line == 1

    def test_module_variable_annotated(self):
        indexer = PythonIndexer()
        source = "timeout: int = 30"
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "variable"
        assert c.qualname == "timeout"
        assert c.role is None  # lowercase is not a const

    def test_module_variable_annotation_only(self):
        indexer = PythonIndexer()
        source = "name: str"
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "variable"
        assert c.qualname == "name"

    def test_class_field(self):
        indexer = PythonIndexer()
        source = """
class User:
    role: str = "user"
"""
        constructs = indexer.index_file(source, "test.py")

        # Now emits both class and field
        assert len(constructs) == 2
        class_c = [c for c in constructs if c.kind == "class"][0]
        assert class_c.qualname == "User"
        field_c = [c for c in constructs if c.kind == "field"][0]
        assert field_c.qualname == "User.role"
        assert field_c.role is None

    def test_class_field_unannotated(self):
        indexer = PythonIndexer()
        source = """
class Config:
    MAX_SIZE = 100
"""
        constructs = indexer.index_file(source, "test.py")

        # Now emits both class and field
        assert len(constructs) == 2
        field_c = [c for c in constructs if c.kind == "field"][0]
        assert field_c.qualname == "Config.MAX_SIZE"
        assert field_c.role == "const"

    def test_class_method(self):
        indexer = PythonIndexer()
        source = """
class User:
    def save(self, path: str = "tmp") -> None:
        pass
"""
        constructs = indexer.index_file(source, "test.py")

        # Now emits both class and method
        assert len(constructs) == 2
        method_c = [c for c in constructs if c.kind == "method"][0]
        assert method_c.qualname == "User.save"
        assert method_c.start_line == 3
        assert method_c.end_line == 4

    def test_decorated_method(self):
        indexer = PythonIndexer()
        source = """
class User:
    @property
    def name(self) -> str:
        return self._name
"""
        constructs = indexer.index_file(source, "test.py")

        # Now emits both class and method
        assert len(constructs) == 2
        method_c = [c for c in constructs if c.kind == "method"][0]
        assert method_c.qualname == "User.name"
        assert method_c.start_line == 3  # Decorator line
        assert method_c.end_line == 5

    def test_find_construct(self):
        indexer = PythonIndexer()
        source = """
MAX_RETRIES = 5

class User:
    role: str = "user"

    def save(self) -> None:
        pass
"""
        construct = indexer.find_construct(source, "test.py", "User.role")
        assert construct is not None
        assert construct.kind == "field"
        assert construct.qualname == "User.role"

    def test_find_construct_with_kind(self):
        indexer = PythonIndexer()
        source = """
class User:
    role: str = "user"
"""
        construct = indexer.find_construct(
            source, "test.py", "User.role", kind="field"
        )
        assert construct is not None
        assert construct.kind == "field"

    def test_find_construct_not_found(self):
        indexer = PythonIndexer()
        source = "x = 1"
        construct = indexer.find_construct(source, "test.py", "y")
        assert construct is None

    def test_multiple_constructs(self):
        indexer = PythonIndexer()
        source = """
MAX_RETRIES = 5
TIMEOUT: int = 30

class User:
    role: str = "user"
    count = 0

    def save(self) -> None:
        pass

    @classmethod
    def create(cls) -> "User":
        return cls()
"""
        constructs = indexer.index_file(source, "test.py")

        names = [c.qualname for c in constructs]
        assert "MAX_RETRIES" in names
        assert "TIMEOUT" in names
        assert "User.role" in names
        assert "User.count" in names
        assert "User.save" in names
        assert "User.create" in names

    def test_module_function(self):
        """Plain module-level function is indexed with kind='function'."""
        indexer = PythonIndexer()
        source = """
def create_order(user_id: int) -> dict:
    return {"user_id": user_id}
"""
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "function"
        assert c.qualname == "create_order"
        assert c.start_line == 2
        assert c.end_line == 3

    def test_module_function_decorated(self):
        """Decorated function includes decorator in line range."""
        indexer = PythonIndexer()
        source = """
@cache
@validate
def process_data(data: list) -> list:
    return data
"""
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "function"
        assert c.qualname == "process_data"
        assert c.start_line == 2  # Decorator line
        assert c.definition_line == 4  # Actual def line
        assert c.end_line == 5

    def test_module_function_fingerprints(self):
        """Changing function body changes body_hash, signature stays same."""
        indexer = PythonIndexer()
        source1 = """
def greet(name: str) -> str:
    return f"Hello, {name}"
"""
        source2 = """
def greet(name: str) -> str:
    return f"Hi, {name}"
"""
        c1 = indexer.index_file(source1, "test.py")[0]
        c2 = indexer.index_file(source2, "test.py")[0]

        assert c1.interface_hash == c2.interface_hash  # Same signature
        assert c1.body_hash != c2.body_hash  # Different body

    def test_module_function_no_types(self):
        """Function without type annotations is indexed correctly."""
        indexer = PythonIndexer()
        source = """
def process(data, limit=10, verbose=False):
    return data[:limit]
"""
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "function"
        assert c.qualname == "process"
        assert c.interface_hash  # Has a hash even without types
        assert c.body_hash  # Has body hash

    def test_module_function_async(self):
        """Async module-level function is indexed with kind='function'."""
        indexer = PythonIndexer()
        source = """
async def fetch_data(url: str) -> dict:
    return {}
"""
        constructs = indexer.index_file(source, "test.py")

        assert len(constructs) == 1
        c = constructs[0]
        assert c.kind == "function"
        assert c.qualname == "fetch_data"

    def test_find_construct_function_by_qualname(self):
        """find_construct() locates module-level function by qualname."""
        indexer = PythonIndexer()
        source = """
def helper():
    pass
"""
        c = indexer.find_construct(source, "test.py", "helper")
        assert c is not None
        assert c.kind == "function"

    def test_find_construct_function_with_kind_filter(self):
        """find_construct() locates function when kind='function' is specified."""
        indexer = PythonIndexer()
        source = """
helper = "value"

def helper():
    pass
"""
        # Without kind filter, ambiguous (returns None since multiple matches)
        c = indexer.find_construct(source, "test.py", "helper")
        assert c is None

        # With kind filter, finds the function
        c = indexer.find_construct(source, "test.py", "helper", kind="function")
        assert c is not None
        assert c.kind == "function"


class TestFingerprinting:
    """Tests for fingerprint computation."""

    def test_whitespace_ignored(self):
        indexer = PythonIndexer()
        source1 = "x = 5"
        source2 = "x  =  5"

        c1 = indexer.index_file(source1, "test.py")[0]
        c2 = indexer.index_file(source2, "test.py")[0]

        assert c1.interface_hash == c2.interface_hash
        assert c1.body_hash == c2.body_hash

    def test_value_change_detected(self):
        indexer = PythonIndexer()
        source1 = "x = 5"
        source2 = "x = 10"

        c1 = indexer.index_file(source1, "test.py")[0]
        c2 = indexer.index_file(source2, "test.py")[0]

        assert c1.interface_hash == c2.interface_hash  # Same interface
        assert c1.body_hash != c2.body_hash  # Different body

    def test_type_annotation_change_detected(self):
        indexer = PythonIndexer()
        source1 = "x: int = 5"
        source2 = "x: float = 5"

        c1 = indexer.index_file(source1, "test.py")[0]
        c2 = indexer.index_file(source2, "test.py")[0]

        assert c1.interface_hash != c2.interface_hash  # Different interface
        assert c1.body_hash == c2.body_hash  # Same body

    def test_annotation_added_detected(self):
        indexer = PythonIndexer()
        source1 = "x = 5"
        source2 = "x: int = 5"

        c1 = indexer.index_file(source1, "test.py")[0]
        c2 = indexer.index_file(source2, "test.py")[0]

        assert c1.interface_hash != c2.interface_hash  # Different interface

    def test_method_param_default_change(self):
        indexer = PythonIndexer()
        source1 = """
class C:
    def f(self, x=1):
        pass
"""
        source2 = """
class C:
    def f(self, x=2):
        pass
"""
        c1 = [c for c in indexer.index_file(source1, "test.py") if c.kind == "method"][0]
        c2 = [c for c in indexer.index_file(source2, "test.py") if c.kind == "method"][0]

        assert c1.interface_hash != c2.interface_hash  # Param defaults in interface

    def test_method_body_change(self):
        indexer = PythonIndexer()
        source1 = """
class C:
    def f(self):
        return 1
"""
        source2 = """
class C:
    def f(self):
        return 2
"""
        c1 = [c for c in indexer.index_file(source1, "test.py") if c.kind == "method"][0]
        c2 = [c for c in indexer.index_file(source2, "test.py") if c.kind == "method"][0]

        assert c1.interface_hash == c2.interface_hash  # Same interface
        assert c1.body_hash != c2.body_hash  # Different body

    def test_comment_ignored(self):
        indexer = PythonIndexer()
        source1 = """
class C:
    def f(self):
        return 1
"""
        source2 = """
class C:
    def f(self):
        # comment
        return 1
"""
        c1 = [c for c in indexer.index_file(source1, "test.py") if c.kind == "method"][0]
        c2 = [c for c in indexer.index_file(source2, "test.py") if c.kind == "method"][0]

        # Both hashes should be the same since comments are ignored
        assert c1.body_hash == c2.body_hash

    def test_decorator_affects_interface(self):
        indexer = PythonIndexer()
        source1 = """
class C:
    def f(self):
        pass
"""
        source2 = """
class C:
    @property
    def f(self):
        pass
"""
        c1 = [c for c in indexer.index_file(source1, "test.py") if c.kind == "method"][0]
        c2 = [c for c in indexer.index_file(source2, "test.py") if c.kind == "method"][0]

        assert c1.interface_hash != c2.interface_hash  # Decorator changes interface


class TestSemanticModels:
    """Tests for semantic data models."""

    def test_semantic_target_to_dict(self):
        from codesub.models import SemanticTarget

        target = SemanticTarget(
            language="python",
            kind="field",
            qualname="User.role",
            role=None,
            interface_hash="abc123",
            body_hash="def456",
        )

        data = target.to_dict()
        assert data["language"] == "python"
        assert data["kind"] == "field"
        assert data["qualname"] == "User.role"
        assert data["interface_hash"] == "abc123"
        assert data["body_hash"] == "def456"

    def test_semantic_target_from_dict(self):
        from codesub.models import SemanticTarget

        data = {
            "language": "python",
            "kind": "method",
            "qualname": "User.save",
            "role": None,
            "interface_hash": "abc",
            "body_hash": "def",
            "fingerprint_version": 1,
        }

        target = SemanticTarget.from_dict(data)
        assert target.language == "python"
        assert target.kind == "method"
        assert target.qualname == "User.save"

    def test_subscription_with_semantic(self):
        from codesub.models import SemanticTarget, Subscription

        semantic = SemanticTarget(
            language="python",
            kind="field",
            qualname="Config.TIMEOUT",
            role="const",
            interface_hash="abc",
            body_hash="def",
        )

        sub = Subscription.create(
            path="config.py",
            start_line=10,
            end_line=10,
            semantic=semantic,
        )

        assert sub.semantic is not None
        assert sub.semantic.qualname == "Config.TIMEOUT"

        # Round-trip through dict
        data = sub.to_dict()
        assert "semantic" in data

        restored = Subscription.from_dict(data)
        assert restored.semantic is not None
        assert restored.semantic.qualname == "Config.TIMEOUT"
