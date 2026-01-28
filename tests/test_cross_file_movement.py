"""Tests for cross-file construct movement detection (Stage 3)."""

import subprocess

import pytest

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
def cross_file_repo(tmp_path):
    """Create a git repo with Python files for cross-file testing."""
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    # Create initial Python file with a constant
    write_file(
        tmp_path / "config.py",
        '''"""Configuration module."""

MAX_RETRIES = 5
TIMEOUT: int = 30
''',
    )

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


class TestCrossFileMovement:
    """Tests for cross-file construct movement detection."""

    def test_construct_moved_to_different_file(self, cross_file_repo):
        """Construct moved from config.py to constants.py is detected."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Get initial fingerprints
        source = (cross_file_repo / "config.py").read_text()
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

        # Move construct to new file
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

MAX_RETRIES = 5
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Move MAX_RETRIES to constants.py")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should have a proposal with moved_cross_file reason
        assert len(result.proposals) == 1
        assert "moved_cross_file" in result.proposals[0].reasons
        assert result.proposals[0].new_path == "constants.py"
        assert result.proposals[0].confidence == "high"  # exact match

        # No trigger (content unchanged)
        assert len(result.triggers) == 0

    def test_construct_moved_with_content_change(self, cross_file_repo):
        """Construct moved AND modified triggers CONTENT change."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Move construct to new file AND change value
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

MAX_RETRIES = 10
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Move and change MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should have proposal AND trigger
        assert len(result.proposals) == 1
        assert "moved_cross_file" in result.proposals[0].reasons
        assert result.proposals[0].new_path == "constants.py"
        # Interface-only match since body changed (value changed)
        # interface_hash same, body_hash different → interface tier → low confidence
        assert result.proposals[0].confidence == "low"

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons

    def test_construct_moved_with_interface_change(self, cross_file_repo):
        """Construct moved AND type changed triggers STRUCTURAL change."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "TIMEOUT")

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

        # Move construct to new file AND change type
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 5
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

TIMEOUT: float = 30
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Move and change TIMEOUT type")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should have proposal AND trigger
        assert len(result.proposals) == 1
        assert "moved_cross_file" in result.proposals[0].reasons
        # Body-only match since interface changed (type annotation changed)
        # interface_hash different, body_hash same → body tier → medium confidence
        assert result.proposals[0].confidence == "medium"

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"
        assert "interface_changed" in result.triggers[0].reasons

    def test_original_file_deleted_construct_moved(self, cross_file_repo):
        """Construct found when original file is deleted.

        Note: Git may detect this as a file rename (if content is similar enough),
        in which case Stage 1 finds it via rename_map. Otherwise Stage 3 finds it
        via cross-file search. Both are valid outcomes.
        """
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Delete original file and create new one with the construct
        (cross_file_repo / "config.py").unlink()
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

MAX_RETRIES = 5
TIMEOUT: int = 30
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Delete config.py, move to constants.py")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find the construct (either via rename detection or cross-file search)
        assert len(result.proposals) == 1
        assert result.proposals[0].new_path == "constants.py"
        # Either git detected it as a rename, or Stage 3 found it
        assert "rename" in result.proposals[0].reasons or "moved_cross_file" in result.proposals[0].reasons

    def test_duplicates_no_trigger_by_default(self, cross_file_repo):
        """Duplicates with trigger_on_duplicate=False returns unchanged."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Default: trigger_on_duplicate=False
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

        # Remove from config.py, add to TWO different files (duplicate)
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

MAX_RETRIES = 5
''',
        )
        write_file(
            cross_file_repo / "defaults.py",
            '''"""Defaults module."""

MAX_RETRIES = 5
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Duplicate MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Default: no trigger, no proposal, treated as unchanged
        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 1

    def test_duplicates_trigger_when_enabled(self, cross_file_repo):
        """Duplicates with trigger_on_duplicate=True returns AMBIGUOUS trigger."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

        # Enable trigger_on_duplicate
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
            trigger_on_duplicate=True,
        )

        base_ref = repo.resolve_ref("HEAD")

        # Remove from config.py, add to TWO different files (duplicate)
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

MAX_RETRIES = 5
''',
        )
        write_file(
            cross_file_repo / "defaults.py",
            '''"""Defaults module."""

MAX_RETRIES = 5
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Duplicate MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should get AMBIGUOUS trigger with locations
        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "AMBIGUOUS"
        assert "duplicate_found" in result.triggers[0].reasons
        assert result.triggers[0].details is not None
        assert "locations" in result.triggers[0].details
        assert len(result.triggers[0].details["locations"]) == 2

        # No proposal when ambiguous
        assert len(result.proposals) == 0

    def test_language_boundary_enforced(self, cross_file_repo):
        """Python construct not matched in Java file with same content."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Remove from Python file, add similar construct to Java file
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "Config.java",
            '''public class Config {
    public static final int MAX_RETRIES = 5;
}
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Move to Java")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should NOT find in Java file, should be MISSING
        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"
        assert "semantic_target_missing" in result.triggers[0].reasons
        assert len(result.proposals) == 0

    def test_construct_not_found_is_missing(self, cross_file_repo):
        """Construct not found anywhere returns MISSING trigger."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Remove construct entirely
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Remove MAX_RETRIES")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"
        assert "semantic_target_missing" in result.triggers[0].reasons

    def test_construct_renamed_and_moved(self, cross_file_repo):
        """Construct renamed AND moved to different file is detected via hash."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Rename construct AND move to different file
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "constants.py",
            '''"""Constants module."""

RETRY_COUNT = 5
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Rename and move")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find via hash matching (exact match - same interface, same body)
        assert len(result.proposals) == 1
        assert "moved_cross_file" in result.proposals[0].reasons
        assert result.proposals[0].new_path == "constants.py"
        assert result.proposals[0].new_qualname == "RETRY_COUNT"

    def test_skips_deleted_files_in_diff(self, cross_file_repo):
        """Deleted files in diff are not searched."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        # Create a second file
        write_file(
            cross_file_repo / "other.py",
            '''"""Other module."""

OTHER_VAR = 1
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Add other.py")

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Remove from config.py, delete other.py (no new home for construct)
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        (cross_file_repo / "other.py").unlink()
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Remove construct and delete other.py")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should not find in deleted file, should be MISSING
        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"

    def test_construct_moved_to_new_file(self, cross_file_repo):
        """Construct moved to newly created file (status=A) is detected."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()

        source = (cross_file_repo / "config.py").read_text()
        construct = indexer.find_construct(source, "config.py", "MAX_RETRIES")

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

        # Remove from config.py, add to brand new file
        write_file(
            cross_file_repo / "config.py",
            '''"""Configuration module."""

TIMEOUT: int = 30
''',
        )
        write_file(
            cross_file_repo / "brand_new.py",
            '''"""Brand new module."""

MAX_RETRIES = 5
''',
        )
        run_git(cross_file_repo, "add", ".")
        run_git(cross_file_repo, "commit", "-m", "Move to brand new file")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find in the new file
        assert len(result.proposals) == 1
        assert "moved_cross_file" in result.proposals[0].reasons
        assert result.proposals[0].new_path == "brand_new.py"


class TestSubscriptionSerialization:
    """Tests for trigger_on_duplicate serialization."""

    def test_to_dict_includes_trigger_on_duplicate(self):
        """Subscription.to_dict includes trigger_on_duplicate field."""
        sub = Subscription.create(
            path="test.py",
            start_line=1,
            end_line=1,
            trigger_on_duplicate=True,
        )

        data = sub.to_dict()
        assert "trigger_on_duplicate" in data
        assert data["trigger_on_duplicate"] is True

    def test_from_dict_defaults_to_false(self):
        """Subscription.from_dict defaults trigger_on_duplicate to False."""
        data = {
            "id": "test-id",
            "path": "test.py",
            "start_line": 1,
            "end_line": 1,
            "active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        sub = Subscription.from_dict(data)
        assert sub.trigger_on_duplicate is False

    def test_from_dict_reads_trigger_on_duplicate(self):
        """Subscription.from_dict reads trigger_on_duplicate field."""
        data = {
            "id": "test-id",
            "path": "test.py",
            "start_line": 1,
            "end_line": 1,
            "active": True,
            "trigger_on_duplicate": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        sub = Subscription.from_dict(data)
        assert sub.trigger_on_duplicate is True

    def test_create_with_trigger_on_duplicate(self):
        """Subscription.create accepts trigger_on_duplicate parameter."""
        sub = Subscription.create(
            path="test.py",
            start_line=1,
            end_line=1,
            trigger_on_duplicate=True,
        )

        assert sub.trigger_on_duplicate is True

    def test_create_defaults_trigger_on_duplicate_to_false(self):
        """Subscription.create defaults trigger_on_duplicate to False."""
        sub = Subscription.create(
            path="test.py",
            start_line=1,
            end_line=1,
        )

        assert sub.trigger_on_duplicate is False


class TestFindHashCandidates:
    """Tests for the _find_hash_candidates helper method."""

    def test_exact_match_returns_exact_tier(self, cross_file_repo):
        """Exact match (both hashes) returns 'exact' tier."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()
        source = (cross_file_repo / "config.py").read_text()
        constructs = indexer.index_file(source, "config.py")
        max_retries = next(c for c in constructs if c.qualname == "MAX_RETRIES")

        semantic = SemanticTarget(
            language="python",
            kind=max_retries.kind,
            qualname="DIFFERENT_NAME",  # Different name, same hashes
            interface_hash=max_retries.interface_hash,
            body_hash=max_retries.body_hash,
        )

        matches, tier = detector._find_hash_candidates(semantic, constructs)

        assert len(matches) == 1
        assert tier == "exact"
        assert matches[0].qualname == "MAX_RETRIES"

    def test_body_only_match_returns_body_tier(self, cross_file_repo):
        """Body-only match returns 'body' tier."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()
        source = (cross_file_repo / "config.py").read_text()
        constructs = indexer.index_file(source, "config.py")
        max_retries = next(c for c in constructs if c.qualname == "MAX_RETRIES")

        semantic = SemanticTarget(
            language="python",
            kind=max_retries.kind,
            qualname="DIFFERENT_NAME",
            interface_hash="different_interface",  # Different interface
            body_hash=max_retries.body_hash,  # Same body
        )

        matches, tier = detector._find_hash_candidates(semantic, constructs)

        assert len(matches) == 1
        assert tier == "body"

    def test_interface_only_match_returns_interface_tier(self, cross_file_repo):
        """Interface-only match returns 'interface' tier."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()
        source = (cross_file_repo / "config.py").read_text()
        constructs = indexer.index_file(source, "config.py")
        max_retries = next(c for c in constructs if c.qualname == "MAX_RETRIES")

        semantic = SemanticTarget(
            language="python",
            kind=max_retries.kind,
            qualname="DIFFERENT_NAME",
            interface_hash=max_retries.interface_hash,  # Same interface
            body_hash="different_body",  # Different body
        )

        matches, tier = detector._find_hash_candidates(semantic, constructs)

        assert len(matches) == 1
        assert tier == "interface"

    def test_no_match_returns_none_tier(self, cross_file_repo):
        """No match returns empty list and 'none' tier."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()
        source = (cross_file_repo / "config.py").read_text()
        constructs = indexer.index_file(source, "config.py")

        semantic = SemanticTarget(
            language="python",
            kind="variable",
            qualname="NONEXISTENT",
            interface_hash="no_match",
            body_hash="no_match",
        )

        matches, tier = detector._find_hash_candidates(semantic, constructs)

        assert len(matches) == 0
        assert tier == "none"

    def test_multiple_matches_all_returned(self, cross_file_repo):
        """Multiple matches are all returned."""
        repo = GitRepo(cross_file_repo)
        detector = Detector(repo)

        # Create file with duplicate values
        write_file(
            cross_file_repo / "dupes.py",
            '''"""Duplicates module."""

VAR_A = 5
VAR_B = 5
''',
        )

        from codesub.semantic import PythonIndexer

        indexer = PythonIndexer()
        source = (cross_file_repo / "dupes.py").read_text()
        constructs = indexer.index_file(source, "dupes.py")
        var_a = next(c for c in constructs if c.qualname == "VAR_A")

        semantic = SemanticTarget(
            language="python",
            kind=var_a.kind,
            qualname="DIFFERENT",
            interface_hash=var_a.interface_hash,
            body_hash=var_a.body_hash,
        )

        matches, tier = detector._find_hash_candidates(semantic, constructs)

        # Both VAR_A and VAR_B should match (same value = same hashes)
        assert len(matches) == 2
        assert tier == "exact"
