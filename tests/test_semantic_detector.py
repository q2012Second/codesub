"""Integration tests for semantic subscription detection."""

import os
import pytest
import tempfile
import subprocess
from pathlib import Path

from codesub.config_store import ConfigStore
from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import SemanticTarget, Subscription


def run_git(cwd, *args):
    """Run a git command in the given directory."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write_file(path, content):
    """Write content to a file."""
    path.write_text(content)


@pytest.fixture
def semantic_repo(tmp_path):
    """Create a git repo with Python files for semantic testing."""
    # Initialize git repo
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    # Create initial Python file
    code_file = tmp_path / "config.py"
    write_file(
        code_file,
        '''"""Configuration module."""

MAX_RETRIES = 5
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
    )

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


class TestSemanticDetector:
    """Tests for semantic change detection."""

    def test_no_change_detected(self, semantic_repo):
        """Semantic subscription unchanged when no changes made."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        # Create subscription to MAX_RETRIES
        sub = Subscription.create(
            path="config.py",
            start_line=3,
            end_line=3,
            semantic=SemanticTarget(
                language="python",
                kind="variable",
                qualname="MAX_RETRIES",
                role="const",
                interface_hash="d1ffa42d3fae5078",  # Computed from the indexer
                body_hash="ef2d127de37b942b",
            ),
        )

        base_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, base_ref)

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 1

    def test_value_change_triggers_content(self, semantic_repo):
        """Changing value triggers CONTENT change."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Modify the value
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 10
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Change MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons

    def test_type_change_triggers_structural(self, semantic_repo):
        """Changing type annotation triggers STRUCTURAL change."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints for TIMEOUT (which has type annotation)
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "TIMEOUT")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change the type annotation
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 5
TIMEOUT: float = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Change TIMEOUT type")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"
        assert "interface_changed" in result.triggers[0].reasons

    def test_line_shift_creates_proposal(self, semantic_repo):
        """Moving construct creates proposal with new line numbers."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Add lines before MAX_RETRIES
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

# Added comment
# Another comment

MAX_RETRIES = 5
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Add comments")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 0  # No trigger (content unchanged)
        assert len(result.proposals) == 1
        assert result.proposals[0].reasons == ["line_shift"]
        assert result.proposals[0].new_start == 6  # Shifted down by 3 lines

    def test_rename_creates_proposal(self, semantic_repo):
        """Renaming construct creates proposal with new qualname."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Rename the variable
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

RETRY_COUNT = 5
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Rename MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find via hash matching since content is the same
        assert len(result.proposals) == 1
        assert result.proposals[0].new_qualname == "RETRY_COUNT"
        assert "semantic_location" in result.proposals[0].reasons

    def test_deleted_construct_triggers_missing(self, semantic_repo):
        """Deleting construct triggers MISSING."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Delete the variable
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Delete MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"
        assert "semantic_target_missing" in result.triggers[0].reasons

    def test_cosmetic_change_no_trigger(self, semantic_repo):
        """Whitespace/formatting changes don't trigger."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Add extra whitespace (cosmetic change)
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES  =  5
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Cosmetic whitespace")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # No trigger because whitespace is normalized
        assert len(result.triggers) == 0
        assert len(result.unchanged) == 1

    def test_method_body_change(self, semantic_repo):
        """Changing method body triggers CONTENT."""
        repo = GitRepo(semantic_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (semantic_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "Config.validate")

        # Create subscription
        sub = Subscription.create(
            path="config.py",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change method body
        write_file(
            semantic_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 5
TIMEOUT: int = 30

class Config:
    debug: bool = False

    def validate(self) -> bool:
        return self.debug or True
''',
        )
        run_git(semantic_repo, "add", ".")
        run_git(semantic_repo, "commit", "-m", "Change validate body")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons
