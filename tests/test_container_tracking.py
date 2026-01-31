"""
Comprehensive tests for container/aggregate tracking.

Tests cover:
- Container subscription creation with baseline member capture
- Member change detection (CONTENT, STRUCTURAL, ADDED, MISSING)
- Container rename detection with relative ID matching
- Container interface changes (decorators, inheritance)
- Private member handling
- Java container tracking
- Updater baseline recapture
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from codesub.detector import Detector
from codesub.git_repo import GitRepo
from codesub.models import (
    CONTAINER_KINDS,
    MemberFingerprint,
    SemanticTarget,
    Subscription,
)
from codesub.semantic import PythonIndexer, get_indexer


def run_git(cwd: Path, *args: str) -> None:
    """Run a git command in the given directory."""
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write_file(path: Path, content: str) -> None:
    """Write content to a file."""
    path.write_text(content)


CONTAINER_BASE = '''"""Container tracking test module."""

class User:
    """User model."""

    name: str = ""
    email: str = ""
    _secret: str = "hidden"

    def validate(self) -> bool:
        """Validate user data."""
        return bool(self.name and self.email)

    def _internal_check(self) -> bool:
        """Internal validation."""
        return True

    @property
    def display_name(self) -> str:
        """Get display name."""
        return self.name.title()


class Admin(User):
    """Admin user."""

    role: str = "admin"

    def can_edit(self, resource: str) -> bool:
        """Check edit permission."""
        return True
'''


@pytest.fixture
def container_repo(tmp_path: Path):
    """Create a git repo with container classes for testing."""
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.email", "test@test.com")
    run_git(tmp_path, "config", "user.name", "Test")

    code_file = tmp_path / "models.py"
    write_file(code_file, CONTAINER_BASE)

    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "Initial commit")

    return tmp_path


def create_container_subscription(
    indexer: PythonIndexer,
    source: str,
    path: str,
    container_qualname: str,
    kind: str = "class",
    include_private: bool = False,
    track_decorators: bool = True,
) -> Subscription:
    """Create a container subscription with baseline members captured."""
    # Find container construct
    all_constructs = indexer.index_file(source, path)
    container = indexer.find_construct(source, path, container_qualname, kind)
    assert container is not None, f"Container {container_qualname} not found"

    # Get members
    members = indexer.get_container_members(
        source, path, container_qualname, include_private, constructs=all_constructs
    )

    # Build baseline members with relative IDs
    baseline_members: dict[str, MemberFingerprint] = {}
    for m in members:
        relative_id = m.qualname[len(container_qualname) + 1:]  # Strip container prefix + dot
        baseline_members[relative_id] = MemberFingerprint(
            kind=m.kind,
            interface_hash=m.interface_hash,
            body_hash=m.body_hash,
        )

    return Subscription.create(
        path=path,
        start_line=container.start_line,
        end_line=container.end_line,
        semantic=SemanticTarget(
            language="python",
            kind=kind,
            qualname=container_qualname,
            interface_hash=container.interface_hash,
            body_hash=container.body_hash,
            include_members=True,
            include_private=include_private,
            track_decorators=track_decorators,
            baseline_members=baseline_members,
            baseline_container_qualname=container_qualname,
        ),
    )


class TestContainerKinds:
    """Test CONTAINER_KINDS configuration."""

    def test_python_container_kinds(self):
        """Python supports class and enum containers."""
        assert "class" in CONTAINER_KINDS["python"]
        assert "enum" in CONTAINER_KINDS["python"]

    def test_java_container_kinds(self):
        """Java supports class, interface, and enum containers."""
        assert "class" in CONTAINER_KINDS["java"]
        assert "interface" in CONTAINER_KINDS["java"]
        assert "enum" in CONTAINER_KINDS["java"]


class TestContainerSubscriptionCreation:
    """Test container subscription creation and baseline capture."""

    def test_creates_subscription_with_baseline_members(self, container_repo: Path):
        """Container subscription captures baseline members."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        sub = create_container_subscription(
            indexer, source, "models.py", "User"
        )

        assert sub.semantic is not None
        assert sub.semantic.include_members is True
        assert sub.semantic.baseline_members is not None
        # Should capture: name, email, validate, display_name (not private)
        assert "name" in sub.semantic.baseline_members
        assert "email" in sub.semantic.baseline_members
        assert "validate" in sub.semantic.baseline_members
        assert "display_name" in sub.semantic.baseline_members
        # Private members excluded by default
        assert "_secret" not in sub.semantic.baseline_members
        assert "_internal_check" not in sub.semantic.baseline_members

    def test_includes_private_members_when_enabled(self, container_repo: Path):
        """include_private=True captures private members."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        sub = create_container_subscription(
            indexer, source, "models.py", "User", include_private=True
        )

        assert sub.semantic is not None
        assert sub.semantic.include_private is True
        # Now private members are included
        assert "_secret" in sub.semantic.baseline_members
        assert "_internal_check" in sub.semantic.baseline_members

    def test_baseline_container_qualname_stored(self, container_repo: Path):
        """Stores baseline_container_qualname for rename detection."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        sub = create_container_subscription(
            indexer, source, "models.py", "User"
        )

        assert sub.semantic.baseline_container_qualname == "User"

    def test_member_fingerprints_have_correct_types(self, container_repo: Path):
        """Member fingerprints have kind, interface_hash, and body_hash."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        sub = create_container_subscription(
            indexer, source, "models.py", "User"
        )

        # Check field
        name_fp = sub.semantic.baseline_members["name"]
        assert name_fp.kind == "field"
        assert len(name_fp.interface_hash) > 0
        assert len(name_fp.body_hash) > 0

        # Check method
        validate_fp = sub.semantic.baseline_members["validate"]
        assert validate_fp.kind == "method"


class TestContainerNoChanges:
    """Test no changes detected when container is unchanged."""

    def test_no_trigger_when_unchanged(self, container_repo: Path):
        """No trigger when container and members are unchanged."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        sub = create_container_subscription(
            indexer, source, "models.py", "User"
        )

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, base_ref)

        assert len(result.triggers) == 0
        assert len(result.proposals) == 0
        assert len(result.unchanged) == 1


class TestMemberContentChange:
    """Test member body/value changes (CONTENT)."""

    def test_method_body_change_triggers(self, container_repo: Path):
        """Changing method body triggers AGGREGATE with member_body_changed."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Modify method body
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name and self.email and len(self.name) > 1)"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change validate body")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_body_changed" in trigger.reasons
        assert trigger.details is not None
        # Check member_changes
        member_changes = trigger.details["member_changes"]
        assert len(member_changes) == 1
        assert member_changes[0]["relative_id"] == "validate"
        assert member_changes[0]["change_type"] == "CONTENT"

    def test_field_value_change_triggers(self, container_repo: Path):
        """Changing field default value triggers AGGREGATE."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Modify field value
        new_source = source.replace('name: str = ""', 'name: str = "unknown"')
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change name default")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        member_changes = trigger.details["member_changes"]
        name_change = [c for c in member_changes if c["relative_id"] == "name"][0]
        assert name_change["change_type"] == "CONTENT"


class TestMemberStructuralChange:
    """Test member interface/signature changes (STRUCTURAL)."""

    def test_method_signature_change_triggers(self, container_repo: Path):
        """Changing method signature triggers AGGREGATE with member_interface_changed."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Change method return type
        new_source = source.replace(
            "def validate(self) -> bool:",
            "def validate(self) -> str:"
        ).replace(
            "return bool(self.name and self.email)",
            'return "valid" if self.name and self.email else "invalid"'
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change validate return type")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_interface_changed" in trigger.reasons
        member_changes = trigger.details["member_changes"]
        validate_change = [c for c in member_changes if c["relative_id"] == "validate"][0]
        assert validate_change["change_type"] == "STRUCTURAL"

    def test_field_type_change_triggers(self, container_repo: Path):
        """Changing field type annotation triggers STRUCTURAL."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Change field type
        new_source = source.replace("name: str = ", "name: str | None = ")
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change name type")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        member_changes = trigger.details["member_changes"]
        name_change = [c for c in member_changes if c["relative_id"] == "name"][0]
        assert name_change["change_type"] == "STRUCTURAL"


class TestMemberAdded:
    """Test new member addition detection."""

    def test_new_method_added_triggers(self, container_repo: Path):
        """Adding new method triggers AGGREGATE with member_added."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Add new method
        new_source = source.replace(
            "    @property\n    def display_name",
            "    def greet(self) -> str:\n        return f'Hello, {self.name}!'\n\n    @property\n    def display_name"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Add greet method")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_added" in trigger.reasons
        assert "greet" in trigger.details["members_added"]
        member_changes = trigger.details["member_changes"]
        greet_change = [c for c in member_changes if c["relative_id"] == "greet"][0]
        assert greet_change["change_type"] == "ADDED"

    def test_new_field_added_triggers(self, container_repo: Path):
        """Adding new field triggers AGGREGATE."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Add new field
        new_source = source.replace(
            '    email: str = ""',
            '    email: str = ""\n    age: int = 0'
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Add age field")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "member_added" in trigger.reasons
        assert "age" in trigger.details["members_added"]


class TestMemberRemoved:
    """Test member removal detection (MISSING)."""

    def test_method_removed_triggers(self, container_repo: Path):
        """Removing method triggers AGGREGATE with member_removed."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Remove the validate method
        new_source = source.replace(
            '''    def validate(self) -> bool:
        """Validate user data."""
        return bool(self.name and self.email)

''', '')
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Remove validate method")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_removed" in trigger.reasons
        assert "validate" in trigger.details["members_removed"]
        member_changes = trigger.details["member_changes"]
        validate_change = [c for c in member_changes if c["relative_id"] == "validate"][0]
        assert validate_change["change_type"] == "MISSING"


class TestContainerRename:
    """Test container rename detection with relative ID matching."""

    def test_container_rename_detected(self, container_repo: Path):
        """Container rename triggers with container_renamed."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Rename User to Person
        new_source = source.replace("class User:", "class Person:")
        new_source = new_source.replace("class Admin(User):", "class Admin(Person):")
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Rename User to Person")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should get a proposal (for the rename) but no AGGREGATE trigger
        # since members are unchanged (just container renamed)
        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        assert proposal.new_qualname == "Person"

    def test_container_rename_with_member_change(self, container_repo: Path):
        """Container rename with member change correctly matches by relative ID."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Rename User to Person AND change a method
        new_source = source.replace("class User:", "class Person:")
        new_source = new_source.replace("class Admin(User):", "class Admin(Person):")
        new_source = new_source.replace(
            "return bool(self.name and self.email)",
            "return len(self.name) > 0 and len(self.email) > 0"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Rename User to Person and change validate")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should get AGGREGATE trigger with both rename and member change
        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "container_renamed" in trigger.reasons or len(result.proposals) == 1
        assert "member_body_changed" in trigger.reasons
        # Details should show the rename
        assert trigger.details["container_qualname"] == "Person"
        assert trigger.details["baseline_container_qualname"] == "User"


class TestContainerInterfaceChanges:
    """Test container-level interface changes (decorators, inheritance)."""

    def test_decorator_added_triggers_when_tracking(self, container_repo: Path):
        """Adding decorator triggers when track_decorators=True."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(
            indexer, source, "models.py", "User", track_decorators=True
        )

        # Add decorator
        new_source = source.replace(
            'class User:',
            '@dataclass\nclass User:'
        )
        new_source = "from dataclasses import dataclass\n" + new_source
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Add dataclass decorator")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "container_interface_changed" in trigger.reasons

    def test_no_trigger_for_decorator_when_not_tracking(self, container_repo: Path):
        """No AGGREGATE trigger for decorator change when track_decorators=False.

        Note: Adding a decorator still causes line shifts, so we get a proposal.
        But no AGGREGATE trigger for container_interface_changed.
        """
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(
            indexer, source, "models.py", "User", track_decorators=False
        )

        # Add decorator (this also shifts lines)
        new_source = source.replace(
            'class User:',
            '@dataclass\nclass User:'
        )
        new_source = "from dataclasses import dataclass\n" + new_source
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Add dataclass decorator")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # No AGGREGATE trigger (decorator changes not tracked)
        assert len(result.triggers) == 0
        # But we get a proposal for line shift (import + decorator added lines)
        assert len(result.proposals) == 1
        assert "line_shift" in result.proposals[0].reasons


class TestPrivateMemberHandling:
    """Test private member inclusion/exclusion."""

    def test_private_member_change_not_detected_by_default(self, container_repo: Path):
        """Private member changes are not detected when include_private=False."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(
            indexer, source, "models.py", "User", include_private=False
        )

        # Change private method
        new_source = source.replace(
            "return True",  # _internal_check
            "return False"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change private method")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should be unchanged (private not tracked)
        assert len(result.triggers) == 0
        assert len(result.unchanged) == 1

    def test_private_member_change_detected_when_enabled(self, container_repo: Path):
        """Private member changes are detected when include_private=True."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(
            indexer, source, "models.py", "User", include_private=True
        )

        # Change private method
        new_source = source.replace(
            '"""Internal validation."""\n        return True',
            '"""Internal validation."""\n        return False'
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Change private method")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        member_changes = trigger.details["member_changes"]
        private_change = [c for c in member_changes if c["relative_id"] == "_internal_check"]
        assert len(private_change) == 1
        assert private_change[0]["change_type"] == "CONTENT"


class TestMultipleMemberChanges:
    """Test multiple member changes in single scan."""

    def test_multiple_changes_detected(self, container_repo: Path):
        """Multiple member changes are all detected."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Change method body, field value, and add new method
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return self.name != '' and self.email != ''"
        ).replace(
            'email: str = ""',
            'email: str = "default@example.com"'
        ).replace(
            "    @property\n    def display_name",
            "    def is_active(self) -> bool:\n        return True\n\n    @property\n    def display_name"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Multiple changes")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        # Should have multiple reasons
        reasons = trigger.reasons
        assert "member_body_changed" in reasons
        assert "member_added" in reasons
        # Should have multiple member changes
        member_changes = trigger.details["member_changes"]
        assert len(member_changes) >= 3  # validate, email, is_active


class TestGetContainerMembers:
    """Test get_container_members method in indexers."""

    def test_python_get_container_members(self, container_repo: Path):
        """Python indexer returns correct container members."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        members = indexer.get_container_members(source, "models.py", "User", include_private=False)

        member_names = [m.qualname for m in members]
        assert "User.name" in member_names
        assert "User.email" in member_names
        assert "User.validate" in member_names
        assert "User.display_name" in member_names
        # Private excluded
        assert "User._secret" not in member_names
        assert "User._internal_check" not in member_names

    def test_python_get_container_members_with_private(self, container_repo: Path):
        """Python indexer includes private members when requested."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()

        members = indexer.get_container_members(source, "models.py", "User", include_private=True)

        member_names = [m.qualname for m in members]
        assert "User._secret" in member_names
        assert "User._internal_check" in member_names

    def test_nested_class_members_excluded(self, container_repo: Path):
        """Nested class members are not included in parent's members."""
        # Create file with nested class
        nested_source = '''
class Outer:
    """Outer class."""
    value: int = 1

    class Inner:
        """Inner class."""
        inner_value: int = 2
'''
        write_file(container_repo / "nested.py", nested_source)

        indexer = PythonIndexer()
        members = indexer.get_container_members(nested_source, "nested.py", "Outer", include_private=False)

        member_names = [m.qualname for m in members]
        assert "Outer.value" in member_names
        assert "Outer.Inner" in member_names
        # Inner's members should NOT be in Outer's members
        assert "Outer.Inner.inner_value" not in member_names


class TestJavaContainerTracking:
    """Test container tracking for Java."""

    @pytest.fixture
    def java_container_repo(self, tmp_path: Path):
        """Create a git repo with Java container classes."""
        run_git(tmp_path, "init")
        run_git(tmp_path, "config", "user.email", "test@test.com")
        run_git(tmp_path, "config", "user.name", "Test")

        java_source = '''public class User {
    private String name;
    private String email;

    public User() {}

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean validate() {
        return name != null && email != null;
    }
}
'''
        write_file(tmp_path / "User.java", java_source)
        run_git(tmp_path, "add", ".")
        run_git(tmp_path, "commit", "-m", "Initial commit")

        return tmp_path

    def test_java_get_container_members(self, java_container_repo: Path):
        """Java indexer returns correct container members."""
        from codesub.semantic import JavaIndexer

        indexer = JavaIndexer()
        source = (java_container_repo / "User.java").read_text()

        members = indexer.get_container_members(source, "User.java", "User", include_private=False)

        member_names = [m.qualname for m in members]
        assert "User.name" in member_names
        assert "User.email" in member_names
        assert "User.User()" in member_names  # constructor
        assert "User.getName()" in member_names
        assert "User.setName(String)" in member_names
        assert "User.validate()" in member_names

    def test_java_container_member_change_detected(self, java_container_repo: Path):
        """Java container member changes are detected."""
        from codesub.semantic import JavaIndexer

        indexer = JavaIndexer()
        source = (java_container_repo / "User.java").read_text()

        # Create subscription
        all_constructs = indexer.index_file(source, "User.java")
        container = indexer.find_construct(source, "User.java", "User", "class")
        members = indexer.get_container_members(source, "User.java", "User", False, constructs=all_constructs)

        baseline_members: dict[str, MemberFingerprint] = {}
        for m in members:
            relative_id = m.qualname[len("User") + 1:]
            baseline_members[relative_id] = MemberFingerprint(
                kind=m.kind, interface_hash=m.interface_hash, body_hash=m.body_hash
            )

        sub = Subscription.create(
            path="User.java",
            start_line=container.start_line,
            end_line=container.end_line,
            semantic=SemanticTarget(
                language="java",
                kind="class",
                qualname="User",
                interface_hash=container.interface_hash,
                body_hash=container.body_hash,
                include_members=True,
                baseline_members=baseline_members,
                baseline_container_qualname="User",
            ),
        )

        # Modify method
        new_source = source.replace(
            "return name != null && email != null;",
            "return name != null && !name.isEmpty() && email != null;"
        )
        write_file(java_container_repo / "User.java", new_source)
        run_git(java_container_repo, "add", ".")
        run_git(java_container_repo, "commit", "-m", "Change validate")

        repo = GitRepo(java_container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        assert "member_body_changed" in trigger.reasons


class TestUpdateDocDetails:
    """Test that update document includes container details."""

    def test_aggregate_trigger_serialized_correctly(self, container_repo: Path):
        """AGGREGATE trigger details are included in update doc."""
        from codesub.update_doc import result_to_dict

        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Add a method
        new_source = source.replace(
            "    @property\n    def display_name",
            "    def greet(self) -> str:\n        return 'Hello'\n\n    @property\n    def display_name"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Add method")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Convert to dict (as would be written to JSON)
        doc = result_to_dict(result)

        assert len(doc["triggers"]) == 1
        trigger_dict = doc["triggers"][0]
        assert trigger_dict["change_type"] == "AGGREGATE"
        assert "details" in trigger_dict
        assert "member_changes" in trigger_dict["details"]
        assert "members_added" in trigger_dict["details"]


class TestMemberFingerprintSerialization:
    """Test MemberFingerprint serialization."""

    def test_to_dict_from_dict_roundtrip(self):
        """MemberFingerprint can be serialized and deserialized."""
        fp = MemberFingerprint(
            kind="method",
            interface_hash="abc123",
            body_hash="def456",
        )

        data = fp.to_dict()
        restored = MemberFingerprint.from_dict(data)

        assert restored.kind == fp.kind
        assert restored.interface_hash == fp.interface_hash
        assert restored.body_hash == fp.body_hash

    def test_semantic_target_with_members_serialization(self, container_repo: Path):
        """SemanticTarget with baseline_members serializes correctly."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Serialize and deserialize
        sub_dict = sub.to_dict()
        restored = Subscription.from_dict(sub_dict)

        assert restored.semantic.include_members is True
        assert restored.semantic.baseline_members is not None
        assert "validate" in restored.semantic.baseline_members
        assert restored.semantic.baseline_container_qualname == "User"


class TestFormatSubscription:
    """Test container subscription display formatting."""

    def test_format_includes_container_indicator(self, container_repo: Path):
        """format_subscription shows container status."""
        from codesub.utils import format_subscription

        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        formatted = format_subscription(sub)

        assert "[container:" in formatted
        assert "members]" in formatted

    def test_verbose_shows_private_and_decorators(self, container_repo: Path):
        """Verbose format shows include_private and track_decorators."""
        from codesub.utils import format_subscription

        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(
            indexer, source, "models.py", "User",
            include_private=True, track_decorators=False
        )

        formatted = format_subscription(sub, verbose=True)

        assert "Include private: yes" in formatted
        assert "Track decorators: no" in formatted


class TestCLIContainerFlags:
    """Test CLI integration for container flags."""

    def _run_cli(self, args: list[str], cwd: Path, data_dir: Path) -> subprocess.CompletedProcess:
        """Run codesub CLI with CODESUB_DATA_DIR set."""
        import os
        import sys
        env = os.environ.copy()
        env["CODESUB_DATA_DIR"] = str(data_dir)
        return subprocess.run(
            [sys.executable, "-m", "codesub.cli"] + args,
            cwd=cwd, capture_output=True, text=True, env=env
        )

    def test_cli_add_with_include_members(self, container_repo: Path, tmp_path: Path):
        """CLI add with --include-members creates container subscription."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Register project
        result = self._run_cli(["projects", "add", str(container_repo)], container_repo, data_dir)
        assert result.returncode == 0

        # Add container subscription
        result = self._run_cli(
            ["add", "models.py::User", "--include-members"],
            container_repo, data_dir
        )

        assert result.returncode == 0
        assert "Added semantic subscription" in result.stdout

        # List and verify
        result = self._run_cli(["list", "--json"], container_repo, data_dir)
        import json
        data = json.loads(result.stdout)
        assert len(data) == 1
        sub = data[0]
        assert sub["semantic"]["include_members"] is True
        assert sub["semantic"]["baseline_members"] is not None
        assert len(sub["semantic"]["baseline_members"]) > 0

    def test_cli_add_with_include_private(self, container_repo: Path, tmp_path: Path):
        """CLI add with --include-private includes private members."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Register project
        result = self._run_cli(["projects", "add", str(container_repo)], container_repo, data_dir)
        assert result.returncode == 0

        result = self._run_cli(
            ["add", "models.py::User", "--include-members", "--include-private"],
            container_repo, data_dir
        )

        assert result.returncode == 0

        result = self._run_cli(["list", "--json"], container_repo, data_dir)
        import json
        data = json.loads(result.stdout)
        sub = data[0]
        assert sub["semantic"]["include_private"] is True
        # Should have private members
        assert "_secret" in sub["semantic"]["baseline_members"]

    def test_cli_add_with_no_track_decorators(self, container_repo: Path, tmp_path: Path):
        """CLI add with --no-track-decorators disables decorator tracking."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Register project
        result = self._run_cli(["projects", "add", str(container_repo)], container_repo, data_dir)
        assert result.returncode == 0

        result = self._run_cli(
            ["add", "models.py::User", "--include-members", "--no-track-decorators"],
            container_repo, data_dir
        )

        assert result.returncode == 0

        result = self._run_cli(["list", "--json"], container_repo, data_dir)
        import json
        data = json.loads(result.stdout)
        sub = data[0]
        assert sub["semantic"]["track_decorators"] is False

    def test_cli_rejects_include_members_for_non_container(self, container_repo: Path, tmp_path: Path):
        """CLI rejects --include-members for non-container construct."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        # Register project
        result = self._run_cli(["projects", "add", str(container_repo)], container_repo, data_dir)
        assert result.returncode == 0

        # Try to add a method with --include-members
        result = self._run_cli(
            ["add", "models.py::User.validate", "--include-members"],
            container_repo, data_dir
        )

        assert result.returncode == 1
        # Error message is in stdout (click exception output)
        output = (result.stdout + result.stderr).lower()
        assert "not a container" in output or "container kinds" in output


class TestUpdaterBaselineRecapture:
    """Test updater baseline member recapture after applying proposals."""

    def test_recaptures_baseline_after_apply(self, container_repo: Path):
        """Updater recaptures baseline members after applying proposals."""
        from codesub.config_store import ConfigStore
        from codesub.updater import Updater

        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Get HEAD ref for init
        base_ref = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=container_repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        # Save subscription to config
        store = ConfigStore(container_repo)
        store.init(base_ref)
        config = store.load()
        config.subscriptions.append(sub)
        store.save(config)

        # Rename User to Person and add a new method
        new_source = source.replace("class User:", "class Person:")
        new_source = new_source.replace("class Admin(User):", "class Admin(Person):")
        new_source = new_source.replace(
            "    @property\n    def display_name",
            "    def greet(self) -> str:\n        return 'Hi'\n\n    @property\n    def display_name"
        )
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Rename User to Person and add greet")

        target_ref = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=container_repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        # Create update document with proposal
        update_data = {
            "target_ref": target_ref,
            "proposals": [{
                "subscription_id": sub.id,
                "new_path": "models.py",
                "new_start": 3,
                "new_end": 25,  # Adjusted for new method
                "new_qualname": "Person",
                "new_kind": "class",
            }]
        }

        repo = GitRepo(container_repo)
        updater = Updater(store, repo)
        applied, warnings = updater.apply(update_data)

        assert sub.id in applied
        assert len(warnings) == 0

        # Reload config and verify baseline was recaptured
        config = store.load()
        updated_sub = config.subscriptions[0]

        # Should have updated qualname
        assert updated_sub.semantic.qualname == "Person"
        assert updated_sub.semantic.baseline_container_qualname == "Person"

        # Should have recaptured baseline members with new method
        assert "greet" in updated_sub.semantic.baseline_members
        assert "validate" in updated_sub.semantic.baseline_members

    def test_recapture_handles_member_rename(self, container_repo: Path):
        """Updater recaptures with current member names after container rename."""
        from codesub.config_store import ConfigStore
        from codesub.updater import Updater

        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        base_ref = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=container_repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        store = ConfigStore(container_repo)
        store.init(base_ref)
        config = store.load()
        config.subscriptions.append(sub)
        store.save(config)

        # Rename class and a method
        new_source = source.replace("class User:", "class Person:")
        new_source = new_source.replace("class Admin(User):", "class Admin(Person):")
        new_source = new_source.replace("def validate(", "def is_valid(")
        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Rename class and method")

        target_ref = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=container_repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        update_data = {
            "target_ref": target_ref,
            "proposals": [{
                "subscription_id": sub.id,
                "new_path": "models.py",
                "new_start": 3,
                "new_end": 21,
                "new_qualname": "Person",
            }]
        }

        repo = GitRepo(container_repo)
        updater = Updater(store, repo)
        applied, _ = updater.apply(update_data)

        config = store.load()
        updated_sub = config.subscriptions[0]

        # Baseline members should have current names (not old names)
        assert "is_valid" in updated_sub.semantic.baseline_members
        assert "validate" not in updated_sub.semantic.baseline_members


class TestContainerMoveDetection:
    """Test container move detection via Stage 2/3."""

    def test_container_moved_in_file_detected(self, container_repo: Path):
        """Container moved within file is detected via Stage 2."""
        indexer = PythonIndexer()
        source = (container_repo / "models.py").read_text()
        sub = create_container_subscription(indexer, source, "models.py", "User")

        # Move User class to end of file (after Admin)
        # First remove User class, then append at end
        lines = source.split('\n')
        user_start = None
        user_end = None
        admin_start = None

        for i, line in enumerate(lines):
            if line.startswith('class User:'):
                user_start = i
            if line.startswith('class Admin'):
                admin_start = i
                if user_start is not None:
                    user_end = i
                    break

        # Extract User class
        user_lines = lines[user_start:user_end]
        # Remove from original position and add at end
        new_lines = lines[:user_start] + lines[user_end:]
        new_lines.extend(['', ''] + user_lines)
        new_source = '\n'.join(new_lines)

        write_file(container_repo / "models.py", new_source)
        run_git(container_repo, "add", ".")
        run_git(container_repo, "commit", "-m", "Move User class to end")

        repo = GitRepo(container_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should get a proposal to update location
        assert len(result.proposals) == 1
        proposal = result.proposals[0]
        # Stage 1 finds it at new location, reason is line_shift (position changed)
        assert "line_shift" in proposal.reasons or "hash_match" in proposal.reasons
        # Verify new location is correct
        assert proposal.new_start > proposal.old_start  # Moved down in file


class TestEnumContainer:
    """Test enum as container."""

    @pytest.fixture
    def enum_repo(self, tmp_path: Path):
        """Create a git repo with enum."""
        run_git(tmp_path, "init")
        run_git(tmp_path, "config", "user.email", "test@test.com")
        run_git(tmp_path, "config", "user.name", "Test")

        enum_source = '''"""Status enum."""
from enum import Enum


class Status(Enum):
    """Order status."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"

    def is_final(self) -> bool:
        return self == Status.COMPLETED
'''
        write_file(tmp_path / "status.py", enum_source)
        run_git(tmp_path, "add", ".")
        run_git(tmp_path, "commit", "-m", "Initial commit")

        return tmp_path

    def test_enum_container_tracking(self, enum_repo: Path):
        """Enum containers track members correctly."""
        indexer = PythonIndexer()
        source = (enum_repo / "status.py").read_text()

        # Find enum construct
        all_constructs = indexer.index_file(source, "status.py")
        container = indexer.find_construct(source, "status.py", "Status", "enum")
        assert container is not None

        members = indexer.get_container_members(
            source, "status.py", "Status", False, constructs=all_constructs
        )

        member_names = [m.qualname for m in members]
        assert "Status.PENDING" in member_names
        assert "Status.ACTIVE" in member_names
        assert "Status.COMPLETED" in member_names
        assert "Status.is_final" in member_names

    def test_enum_member_change_detected(self, enum_repo: Path):
        """Enum member value change is detected."""
        indexer = PythonIndexer()
        source = (enum_repo / "status.py").read_text()

        sub = create_container_subscription(
            indexer, source, "status.py", "Status", kind="enum"
        )

        # Change enum value
        new_source = source.replace('PENDING = "pending"', 'PENDING = "waiting"')
        write_file(enum_repo / "status.py", new_source)
        run_git(enum_repo, "add", ".")
        run_git(enum_repo, "commit", "-m", "Change PENDING value")

        repo = GitRepo(enum_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert trigger.change_type == "AGGREGATE"
        member_changes = trigger.details["member_changes"]
        pending_change = [c for c in member_changes if c["relative_id"] == "PENDING"][0]
        assert pending_change["change_type"] == "CONTENT"

    def test_new_enum_member_detected(self, enum_repo: Path):
        """New enum member is detected."""
        indexer = PythonIndexer()
        source = (enum_repo / "status.py").read_text()

        sub = create_container_subscription(
            indexer, source, "status.py", "Status", kind="enum"
        )

        # Add new enum value
        new_source = source.replace(
            '    COMPLETED = "completed"',
            '    COMPLETED = "completed"\n    CANCELLED = "cancelled"'
        )
        write_file(enum_repo / "status.py", new_source)
        run_git(enum_repo, "add", ".")
        run_git(enum_repo, "commit", "-m", "Add CANCELLED")

        repo = GitRepo(enum_repo)
        detector = Detector(repo)
        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "member_added" in trigger.reasons
        assert "CANCELLED" in trigger.details["members_added"]
