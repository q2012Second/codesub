"""
Comprehensive tests for semantic subscriptions across various Python construct types.

Tests cover:
- Module constants (typed and untyped)
- Enum members
- TypedDict fields
- NamedTuple fields
- Dataclass fields
- Class variables
- Methods (static, class, property)

For each construct type, we test:
- Value change → CONTENT trigger
- Type annotation change → STRUCTURAL trigger
- Rename → PROPOSAL
- Delete → MISSING trigger
- Cosmetic change → No trigger
"""

import subprocess
from pathlib import Path

import pytest

from codesub.config_store import ConfigStore
from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import SemanticTarget, Subscription


def run_git(cwd: Path, *args: str) -> None:
    """Run a git command in the given directory."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write_file(path: Path, content: str) -> None:
    """Write content to a file."""
    path.write_text(content)


ADVANCED_TYPES_BASE = '''"""Advanced Python types for semantic subscription testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Dict, Generic, List, NamedTuple, Optional, Protocol, TypedDict, TypeVar

# Module-level typed constant
API_VERSION: str = "v2.0"

class Status(Enum):
    """Status enumeration."""
    PENDING = "pending"
    ACTIVE = "active"

class UserDict(TypedDict):
    """User as TypedDict."""
    id: int
    username: str

class Point(NamedTuple):
    """2D point as NamedTuple."""
    x: float
    y: float

@dataclass
class SimpleData:
    """Simple dataclass."""
    name: str
    value: int

class ServiceConfig:
    """Configuration class."""
    default_timeout: int = 30

class Calculator:
    """Calculator with static methods."""

    @staticmethod
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

class Rectangle(NamedTuple):
    """Rectangle with property."""
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height
'''


@pytest.fixture
def advanced_repo(tmp_path: Path):
    """Create a git repo with advanced Python types."""
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    # Create initial file
    code_file = tmp_path / "types.py"
    write_file(code_file, ADVANCED_TYPES_BASE)

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


def create_subscription(
    path: str,
    qualname: str,
    kind: str,
    start_line: int,
    end_line: int,
    interface_hash: str,
    body_hash: str,
    role: str | None = None,
) -> Subscription:
    """Create a semantic subscription for testing."""
    return Subscription.create(
        path=path,
        start_line=start_line,
        end_line=end_line,
        semantic=SemanticTarget(
            language="python",
            kind=kind,
            qualname=qualname,
            role=role,
            interface_hash=interface_hash,
            body_hash=body_hash,
        ),
    )


class TestModuleConstant:
    """Test semantic detection for typed module constants."""

    def test_value_change_triggers_content(self, advanced_repo: Path):
        """Changing constant value triggers CONTENT."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "API_VERSION")

        sub = create_subscription(
            "types.py", "API_VERSION", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change value
        new_content = ADVANCED_TYPES_BASE.replace(
            'API_VERSION: str = "v2.0"',
            'API_VERSION: str = "v3.0"'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change API version")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons

    def test_type_change_triggers_structural(self, advanced_repo: Path):
        """Changing type annotation triggers STRUCTURAL."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "API_VERSION")

        sub = create_subscription(
            "types.py", "API_VERSION", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change type annotation (str -> int would be weird but tests the detection)
        new_content = ADVANCED_TYPES_BASE.replace(
            'API_VERSION: str = "v2.0"',
            'API_VERSION: int = 2'  # Changed type
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change type annotation")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"

    def test_cosmetic_change_no_trigger(self, advanced_repo: Path):
        """Whitespace changes don't trigger."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "API_VERSION")

        sub = create_subscription(
            "types.py", "API_VERSION", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Add cosmetic whitespace
        new_content = ADVANCED_TYPES_BASE.replace(
            'API_VERSION: str = "v2.0"',
            'API_VERSION:  str  =  "v2.0"'  # Extra whitespace
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Cosmetic whitespace")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 0
        assert len(result.unchanged) == 1


class TestEnumMember:
    """Test semantic detection for enum members."""

    def test_value_change_triggers_content(self, advanced_repo: Path):
        """Changing enum value triggers CONTENT."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Status.PENDING")

        sub = create_subscription(
            "types.py", "Status.PENDING", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change enum value
        new_content = ADVANCED_TYPES_BASE.replace(
            'PENDING = "pending"',
            'PENDING = "waiting"'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change enum value")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"

    def test_rename_creates_proposal(self, advanced_repo: Path):
        """Renaming enum member creates proposal."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Status.PENDING")

        sub = create_subscription(
            "types.py", "Status.PENDING", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Rename enum member (same value)
        new_content = ADVANCED_TYPES_BASE.replace(
            'PENDING = "pending"',
            'WAITING = "pending"'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Rename enum member")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.proposals) == 1
        assert result.proposals[0].new_qualname == "Status.WAITING"

    def test_delete_triggers_missing(self, advanced_repo: Path):
        """Deleting entire class triggers MISSING for its members."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Status.PENDING")

        sub = create_subscription(
            "types.py", "Status.PENDING", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Delete the entire Status enum class
        new_content = ADVANCED_TYPES_BASE.replace(
            '''class Status(Enum):
    """Status enumeration."""
    PENDING = "pending"
    ACTIVE = "active"

''',
            ''
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Delete Status enum")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"
        assert "semantic_target_missing" in result.triggers[0].reasons


class TestTypedDictField:
    """Test semantic detection for TypedDict fields."""

    def test_type_change_triggers_structural(self, advanced_repo: Path):
        """Changing TypedDict field type triggers STRUCTURAL."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "UserDict.id")

        sub = create_subscription(
            "types.py", "UserDict.id", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change field type
        new_content = ADVANCED_TYPES_BASE.replace(
            '    id: int\n    username: str',
            '    id: str\n    username: str'  # int -> str
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change TypedDict field type")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"


class TestDataclassField:
    """Test semantic detection for dataclass fields."""

    def test_default_value_change_triggers_content(self, advanced_repo: Path):
        """Changing dataclass field default triggers CONTENT."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        # First, let's modify the base to have a default value
        base_with_default = ADVANCED_TYPES_BASE.replace(
            '    name: str\n    value: int',
            '    name: str = "default"\n    value: int'
        )
        write_file(advanced_repo / "types.py", base_with_default)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Add default value", "--amend")

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "SimpleData.name")

        sub = create_subscription(
            "types.py", "SimpleData.name", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change default value
        new_content = base_with_default.replace(
            '    name: str = "default"',
            '    name: str = "changed"'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change dataclass default")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"


class TestMethodDetection:
    """Test semantic detection for methods."""

    def test_body_change_triggers_content(self, advanced_repo: Path):
        """Changing method body triggers CONTENT."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Calculator.add")

        sub = create_subscription(
            "types.py", "Calculator.add", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change method body
        new_content = ADVANCED_TYPES_BASE.replace(
            '        return a + b',
            '        return a + b + 0  # Different implementation'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change method body")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"

    def test_signature_change_triggers_structural(self, advanced_repo: Path):
        """Changing method signature triggers STRUCTURAL."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Calculator.add")

        sub = create_subscription(
            "types.py", "Calculator.add", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change method signature (add parameter)
        new_content = ADVANCED_TYPES_BASE.replace(
            'def add(a: float, b: float) -> float:',
            'def add(a: float, b: float, c: float = 0) -> float:'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change method signature")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"

    def test_return_type_change_triggers_structural(self, advanced_repo: Path):
        """Changing return type triggers STRUCTURAL."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Calculator.add")

        sub = create_subscription(
            "types.py", "Calculator.add", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change return type
        new_content = ADVANCED_TYPES_BASE.replace(
            'def add(a: float, b: float) -> float:',
            'def add(a: float, b: float) -> int:'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change return type")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"


class TestPropertyDetection:
    """Test semantic detection for property methods."""

    def test_property_body_change_triggers_content(self, advanced_repo: Path):
        """Changing property body triggers CONTENT."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Rectangle.area")

        sub = create_subscription(
            "types.py", "Rectangle.area", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change property body
        new_content = ADVANCED_TYPES_BASE.replace(
            '        return self.width * self.height',
            '        return self.width * self.height * 1.0'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Change property body")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"


class TestLineShifts:
    """Test that semantic subscriptions handle line shifts correctly."""

    def test_line_shift_creates_proposal_not_trigger(self, advanced_repo: Path):
        """Adding lines before construct creates proposal, not trigger."""
        repo = GitRepo(advanced_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer
        indexer = PythonIndexer()

        source = (advanced_repo / "types.py").read_text()
        c = indexer.find_construct(source, "types.py", "Status.PENDING")
        original_line = c.start_line

        sub = create_subscription(
            "types.py", "Status.PENDING", c.kind, c.start_line, c.end_line,
            c.interface_hash, c.body_hash, c.role
        )

        base_ref = repo.resolve_ref("HEAD")

        # Add lines before the enum
        new_content = ADVANCED_TYPES_BASE.replace(
            'class Status(Enum):',
            '# Added comment 1\n# Added comment 2\n# Added comment 3\n\nclass Status(Enum):'
        )
        write_file(advanced_repo / "types.py", new_content)
        run_git(advanced_repo, "add", ".")
        run_git(advanced_repo, "commit", "-m", "Add comments before enum")

        result = detector.scan([sub], base_ref, repo.resolve_ref("HEAD"))

        # Should have proposal for line shift, not a trigger
        assert len(result.triggers) == 0
        assert len(result.proposals) == 1
        assert result.proposals[0].new_start > original_line
        assert "line_shift" in result.proposals[0].reasons
