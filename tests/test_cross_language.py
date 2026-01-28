"""Integration tests for cross-language scenarios."""

import subprocess
from pathlib import Path

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
def mixed_lang_repo(tmp_path):
    """Create a git repo with both Python and Java files."""
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    # Create Python file
    py_file = tmp_path / "config.py"
    write_file(
        py_file,
        '''"""Configuration module."""

MAX_RETRIES = 5
TIMEOUT: int = 30

class Config:
    debug: bool = False
''',
    )

    # Create Java file
    java_file = tmp_path / "Service.java"
    write_file(
        java_file,
        """public class Service {
    public static final int PORT = 8080;
    private String name;

    public Service(String name) {
        this.name = name;
    }

    public void start() {
        // Start service
    }
}
""",
    )

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


class TestCrossLanguageScanning:
    """Tests for scanning repositories with multiple languages."""

    def test_python_and_java_subscriptions_in_same_scan(self, mixed_lang_repo):
        """Scan correctly handles both Python and Java subscriptions."""
        from codesub.semantic import get_indexer

        repo = GitRepo(mixed_lang_repo)
        detector = Detector(repo)

        # Create Python subscription
        py_indexer = get_indexer("python")
        py_source = (mixed_lang_repo / "config.py").read_text()
        py_construct = py_indexer.find_construct(py_source, "config.py", "MAX_RETRIES")

        py_sub = Subscription.create(
            path="config.py",
            start_line=py_construct.start_line,
            end_line=py_construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=py_construct.kind,
                qualname=py_construct.qualname,
                role=py_construct.role,
                interface_hash=py_construct.interface_hash,
                body_hash=py_construct.body_hash,
            ),
        )

        # Create Java subscription
        java_indexer = get_indexer("java")
        java_source = (mixed_lang_repo / "Service.java").read_text()
        java_construct = java_indexer.find_construct(java_source, "Service.java", "Service.PORT")

        java_sub = Subscription.create(
            path="Service.java",
            start_line=java_construct.start_line,
            end_line=java_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=java_construct.kind,
                qualname=java_construct.qualname,
                role=java_construct.role,
                interface_hash=java_construct.interface_hash,
                body_hash=java_construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # No changes - both should be unchanged
        result = detector.scan([py_sub, java_sub], base_ref, base_ref)

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 2

    def test_python_change_doesnt_affect_java(self, mixed_lang_repo):
        """Changing Python file doesn't affect Java subscriptions."""
        from codesub.semantic import get_indexer

        repo = GitRepo(mixed_lang_repo)
        detector = Detector(repo)

        # Create Python subscription
        py_indexer = get_indexer("python")
        py_source = (mixed_lang_repo / "config.py").read_text()
        py_construct = py_indexer.find_construct(py_source, "config.py", "MAX_RETRIES")

        py_sub = Subscription.create(
            path="config.py",
            start_line=py_construct.start_line,
            end_line=py_construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=py_construct.kind,
                qualname=py_construct.qualname,
                role=py_construct.role,
                interface_hash=py_construct.interface_hash,
                body_hash=py_construct.body_hash,
            ),
        )

        # Create Java subscription
        java_indexer = get_indexer("java")
        java_source = (mixed_lang_repo / "Service.java").read_text()
        java_construct = java_indexer.find_construct(java_source, "Service.java", "Service.PORT")

        java_sub = Subscription.create(
            path="Service.java",
            start_line=java_construct.start_line,
            end_line=java_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=java_construct.kind,
                qualname=java_construct.qualname,
                role=java_construct.role,
                interface_hash=java_construct.interface_hash,
                body_hash=java_construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change only Python file
        write_file(
            mixed_lang_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 10  # Changed
TIMEOUT: int = 30

class Config:
    debug: bool = False
''',
        )
        run_git(mixed_lang_repo, "add", ".")
        run_git(mixed_lang_repo, "commit", "-m", "Change Python")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([py_sub, java_sub], base_ref, target_ref)

        # Python subscription should trigger
        assert len(result.triggers) == 1
        assert result.triggers[0].subscription_id == py_sub.id
        assert result.triggers[0].change_type == "CONTENT"

        # Java subscription should be unchanged
        assert len(result.unchanged) == 1
        assert result.unchanged[0].id == java_sub.id

    def test_java_change_doesnt_affect_python(self, mixed_lang_repo):
        """Changing Java file doesn't affect Python subscriptions."""
        from codesub.semantic import get_indexer

        repo = GitRepo(mixed_lang_repo)
        detector = Detector(repo)

        # Create Python subscription
        py_indexer = get_indexer("python")
        py_source = (mixed_lang_repo / "config.py").read_text()
        py_construct = py_indexer.find_construct(py_source, "config.py", "MAX_RETRIES")

        py_sub = Subscription.create(
            path="config.py",
            start_line=py_construct.start_line,
            end_line=py_construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=py_construct.kind,
                qualname=py_construct.qualname,
                role=py_construct.role,
                interface_hash=py_construct.interface_hash,
                body_hash=py_construct.body_hash,
            ),
        )

        # Create Java subscription
        java_indexer = get_indexer("java")
        java_source = (mixed_lang_repo / "Service.java").read_text()
        java_construct = java_indexer.find_construct(java_source, "Service.java", "Service.PORT")

        java_sub = Subscription.create(
            path="Service.java",
            start_line=java_construct.start_line,
            end_line=java_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=java_construct.kind,
                qualname=java_construct.qualname,
                role=java_construct.role,
                interface_hash=java_construct.interface_hash,
                body_hash=java_construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change only Java file
        write_file(
            mixed_lang_repo / "Service.java",
            """public class Service {
    public static final int PORT = 9090;  // Changed
    private String name;

    public Service(String name) {
        this.name = name;
    }

    public void start() {
        // Start service
    }
}
""",
        )
        run_git(mixed_lang_repo, "add", ".")
        run_git(mixed_lang_repo, "commit", "-m", "Change Java")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([py_sub, java_sub], base_ref, target_ref)

        # Java subscription should trigger
        assert len(result.triggers) == 1
        assert result.triggers[0].subscription_id == java_sub.id
        assert result.triggers[0].change_type == "CONTENT"

        # Python subscription should be unchanged
        assert len(result.unchanged) == 1
        assert result.unchanged[0].id == py_sub.id

    def test_both_languages_changed_independently(self, mixed_lang_repo):
        """Both languages can have independent changes in same scan."""
        from codesub.semantic import get_indexer

        repo = GitRepo(mixed_lang_repo)
        detector = Detector(repo)

        # Create Python subscription
        py_indexer = get_indexer("python")
        py_source = (mixed_lang_repo / "config.py").read_text()
        py_construct = py_indexer.find_construct(py_source, "config.py", "MAX_RETRIES")

        py_sub = Subscription.create(
            path="config.py",
            start_line=py_construct.start_line,
            end_line=py_construct.end_line,
            semantic=SemanticTarget(
                language="python",
                kind=py_construct.kind,
                qualname=py_construct.qualname,
                role=py_construct.role,
                interface_hash=py_construct.interface_hash,
                body_hash=py_construct.body_hash,
            ),
        )

        # Create Java subscription
        java_indexer = get_indexer("java")
        java_source = (mixed_lang_repo / "Service.java").read_text()
        java_construct = java_indexer.find_construct(java_source, "Service.java", "Service.PORT")

        java_sub = Subscription.create(
            path="Service.java",
            start_line=java_construct.start_line,
            end_line=java_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=java_construct.kind,
                qualname=java_construct.qualname,
                role=java_construct.role,
                interface_hash=java_construct.interface_hash,
                body_hash=java_construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change both files
        write_file(
            mixed_lang_repo / "config.py",
            '''"""Configuration module."""

MAX_RETRIES = 10  # Changed
TIMEOUT: int = 30

class Config:
    debug: bool = False
''',
        )
        write_file(
            mixed_lang_repo / "Service.java",
            """public class Service {
    public static final int PORT = 9090;  // Changed
    private String name;

    public Service(String name) {
        this.name = name;
    }

    public void start() {
        // Start service
    }
}
""",
        )
        run_git(mixed_lang_repo, "add", ".")
        run_git(mixed_lang_repo, "commit", "-m", "Change both")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([py_sub, java_sub], base_ref, target_ref)

        # Both subscriptions should trigger
        assert len(result.triggers) == 2
        triggered_ids = {t.subscription_id for t in result.triggers}
        assert py_sub.id in triggered_ids
        assert java_sub.id in triggered_ids

        # Both should be CONTENT changes
        for trigger in result.triggers:
            assert trigger.change_type == "CONTENT"
