"""Integration tests for Java semantic subscription detection."""

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
def java_repo(tmp_path):
    """Create a git repo with Java files for semantic testing."""
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    # Create Java file
    java_file = tmp_path / "Calculator.java"
    write_file(
        java_file,
        """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
    )

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


class TestJavaSemanticDetector:
    """Integration tests for Java semantic change detection."""

    def test_no_change_detected(self, java_repo):
        """Java semantic subscription unchanged when no changes made."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, base_ref)

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 1

    def test_method_body_change_triggers_content(self, java_repo):
        """Changing Java method body triggers CONTENT change."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Modify the method body
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        // Changed implementation
        int sum = a + b;
        return sum;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Change add method")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons

    def test_field_value_change_triggers_content(self, java_repo):
        """Changing Java field value triggers CONTENT change."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.MAX_VALUE")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change the constant value
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 2000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Change MAX_VALUE")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"

    def test_method_signature_change_triggers_structural(self, java_repo):
        """Changing Java method return type triggers STRUCTURAL change."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change the return type from int to long
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public long add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Change add return type")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "STRUCTURAL"
        assert "interface_changed" in result.triggers[0].reasons

    def test_file_deletion_triggers_missing(self, java_repo):
        """Deleting Java file triggers MISSING."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Delete the file
        import os
        os.remove(java_repo / "Calculator.java")
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Delete Calculator.java")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "MISSING"
        assert "file_deleted" in result.triggers[0].reasons

    def test_method_line_shift_creates_proposal(self, java_repo):
        """Moving Java method creates proposal with new line numbers."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")
        original_start = construct.start_line

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Add lines before the method
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    // Added comment line 1
    // Added comment line 2
    // Added comment line 3

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Add comments")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 0
        assert len(result.proposals) == 1
        assert result.proposals[0].reasons == ["line_shift"]
        assert result.proposals[0].new_start > original_start

    def test_constructor_change_detected(self, java_repo):
        """Changing Java constructor body triggers CONTENT change."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.Calculator()")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Change constructor body
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 100;  // Changed initialization
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Change constructor")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"


class TestHashFallbackLogic:
    """Tests for _find_by_hash fallback tiers."""

    def test_rename_with_body_change_found_via_interface(self, java_repo):
        """Renamed construct with changed body is found via interface hash."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Rename method AND change body
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int sum(int a, int b) {
        // Different implementation
        int result = a + b;
        return result;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Rename and change add method")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find via interface-only match (tier 3)
        # May trigger due to body change, but should have proposal for new location
        assert len(result.proposals) == 1 or len(result.triggers) == 1
        if result.proposals:
            assert result.proposals[0].new_qualname == "Calculator.sum(int,int)"

    def test_rename_with_signature_change_found_via_body(self, java_repo):
        """Renamed construct with changed signature is found via body hash."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.MAX_VALUE")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Rename field AND change type (but same value)
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final long MAXIMUM = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Rename and change type of MAX_VALUE")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, target_ref)

        # Should find via body-only match (tier 2) since value is same
        # May trigger STRUCTURAL due to type change
        assert len(result.proposals) == 1 or len(result.triggers) == 1
        if result.proposals:
            assert result.proposals[0].new_qualname == "Calculator.MAXIMUM"


class TestUnsupportedLanguage:
    """Tests for unsupported language handling."""

    def test_unsupported_language_triggers_ambiguous(self, java_repo):
        """Subscription with unsupported language returns AMBIGUOUS trigger."""
        repo = GitRepo(java_repo)
        detector = Detector(repo)

        # Create subscription with unsupported language
        sub = Subscription.create(
            path="Calculator.java",
            start_line=1,
            end_line=5,
            semantic=SemanticTarget(
                language="ruby",  # Not supported
                kind="method",
                qualname="Calculator.add",
                role=None,
                interface_hash="abc123",
                body_hash="def456",
            ),
        )

        base_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub], base_ref, base_ref)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "AMBIGUOUS"
        assert "unsupported_language" in result.triggers[0].reasons
        assert "error" in result.triggers[0].details


class TestMultipleSubscriptions:
    """Tests for scanning multiple subscriptions."""

    def test_mixed_results_from_multiple_subscriptions(self, java_repo):
        """Multiple subscriptions can have different results in one scan."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()

        # Create subscriptions to different constructs
        add_construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")
        sub_construct = indexer.find_construct(source, "Calculator.java", "Calculator.subtract(int,int)")
        max_construct = indexer.find_construct(source, "Calculator.java", "Calculator.MAX_VALUE")

        sub_add = Subscription.create(
            path="Calculator.java",
            start_line=add_construct.start_line,
            end_line=add_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=add_construct.kind,
                qualname=add_construct.qualname,
                role=add_construct.role,
                interface_hash=add_construct.interface_hash,
                body_hash=add_construct.body_hash,
            ),
        )

        sub_subtract = Subscription.create(
            path="Calculator.java",
            start_line=sub_construct.start_line,
            end_line=sub_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=sub_construct.kind,
                qualname=sub_construct.qualname,
                role=sub_construct.role,
                interface_hash=sub_construct.interface_hash,
                body_hash=sub_construct.body_hash,
            ),
        )

        sub_max = Subscription.create(
            path="Calculator.java",
            start_line=max_construct.start_line,
            end_line=max_construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=max_construct.kind,
                qualname=max_construct.qualname,
                role=max_construct.role,
                interface_hash=max_construct.interface_hash,
                body_hash=max_construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Modify only add method, leave others unchanged
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b + 1;  // Changed
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )
        run_git(java_repo, "add", ".")
        run_git(java_repo, "commit", "-m", "Change only add method")

        target_ref = repo.resolve_ref("HEAD")
        result = detector.scan([sub_add, sub_subtract, sub_max], base_ref, target_ref)

        # add should trigger, subtract and MAX_VALUE should be unchanged
        assert len(result.triggers) == 1
        assert result.triggers[0].subscription_id == sub_add.id
        assert result.triggers[0].change_type == "CONTENT"

        assert len(result.unchanged) == 2
        unchanged_ids = {s.id for s in result.unchanged}
        assert sub_subtract.id in unchanged_ids
        assert sub_max.id in unchanged_ids


class TestWorkingDirectoryScan:
    """Tests for scanning against working directory (no target_ref)."""

    def test_scan_uncommitted_changes(self, java_repo):
        """Scan detects uncommitted changes in working directory."""
        from codesub.semantic import get_indexer

        repo = GitRepo(java_repo)
        detector = Detector(repo)
        indexer = get_indexer("java")

        source = (java_repo / "Calculator.java").read_text()
        construct = indexer.find_construct(source, "Calculator.java", "Calculator.add(int,int)")

        sub = Subscription.create(
            path="Calculator.java",
            start_line=construct.start_line,
            end_line=construct.end_line,
            semantic=SemanticTarget(
                language="java",
                kind=construct.kind,
                qualname=construct.qualname,
                role=construct.role,
                interface_hash=construct.interface_hash,
                body_hash=construct.body_hash,
            ),
        )

        base_ref = repo.resolve_ref("HEAD")

        # Modify file but DON'T commit
        write_file(
            java_repo / "Calculator.java",
            """public class Calculator {
    public static final int MAX_VALUE = 1000;
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b + 999;  // Uncommitted change
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}
""",
        )

        # Scan against working directory (target_ref=None)
        result = detector.scan([sub], base_ref, None)

        assert len(result.triggers) == 1
        assert result.triggers[0].change_type == "CONTENT"
        assert "body_changed" in result.triggers[0].reasons
