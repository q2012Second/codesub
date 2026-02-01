"""Tests for inheritance-aware change detection."""

import pytest
from pathlib import Path
import tempfile
import subprocess

from codesub.semantic import (
    PythonIndexer,
    InheritanceResolver,
    get_member_id,
    get_overridden_members,
)
from codesub.git_repo import GitRepo
from codesub.detector import Detector
from codesub.models import MemberFingerprint, Subscription, SemanticTarget


def run_git(path: Path, *args: str) -> str:
    """Run git command in path."""
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def write_file(path: Path, content: str) -> None:
    """Write content to file."""
    path.write_text(content)


@pytest.fixture
def inheritance_repo() -> Path:
    """Create a temp git repo with inheritance hierarchy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        run_git(repo_path, "init")
        run_git(repo_path, "config", "user.email", "test@test.com")
        run_git(repo_path, "config", "user.name", "Test User")

        # Create initial files with inheritance
        source = '''"""Inheritance test module."""

class User:
    """Base user class."""

    name: str = ""
    email: str = ""

    def validate(self) -> bool:
        """Validate user data."""
        return bool(self.name and self.email)

    def save(self) -> None:
        """Save user to database."""
        pass


class Admin(User):
    """Admin user."""

    role: str = "admin"

    def can_edit(self, resource: str) -> bool:
        """Check edit permission."""
        return True


class SuperAdmin(Admin):
    """Super admin with all permissions."""

    super_power: str = "all"

    def can_delete(self) -> bool:
        """Can delete anything."""
        return True
'''
        write_file(repo_path / "models.py", source)

        run_git(repo_path, "add", ".")
        run_git(repo_path, "commit", "-m", "Initial commit")

        yield repo_path


class TestBaseClassExtraction:
    """Tests for extracting base classes from source."""

    def test_python_simple_inheritance(self):
        """Test extracting single base class."""
        source = """
class Admin(User):
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        admin = next(c for c in constructs if c.qualname == "Admin")

        assert admin.base_classes == ("User",)

    def test_python_multiple_inheritance(self):
        """Test extracting multiple base classes."""
        source = """
class Admin(User, Mixin, ABC):
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        admin = next(c for c in constructs if c.qualname == "Admin")

        assert admin.base_classes == ("User", "Mixin", "ABC")

    def test_python_no_inheritance(self):
        """Test class without base classes."""
        source = """
class User:
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        user = next(c for c in constructs if c.qualname == "User")

        assert user.base_classes is None

    def test_python_generic_base(self):
        """Test extracting base from generic class."""
        source = """
class UserList(List[User]):
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        user_list = next(c for c in constructs if c.qualname == "UserList")

        # Should extract "List", not "List[User]"
        assert user_list.base_classes == ("List",)

    def test_python_module_qualified_base(self):
        """Test extracting module-qualified base class."""
        source = """
class Admin(models.User):
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        admin = next(c for c in constructs if c.qualname == "Admin")

        assert admin.base_classes == ("models.User",)

    def test_python_metaclass_not_included(self):
        """Test that metaclass is not included as base class."""
        source = """
class Admin(User, metaclass=ABCMeta):
    pass
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        admin = next(c for c in constructs if c.qualname == "Admin")

        # Should only include User, not metaclass
        assert admin.base_classes == ("User",)


class TestExtractImports:
    """Tests for extracting imports using Tree-sitter."""

    def test_from_import(self):
        """Test from X import Y."""
        source = """
from models import User
"""
        indexer = PythonIndexer()
        imports = indexer.extract_imports(source)

        assert "User" in imports
        assert imports["User"] == ("models", "User")

    def test_from_import_alias(self):
        """Test from X import Y as Z."""
        source = """
from models import User as U
"""
        indexer = PythonIndexer()
        imports = indexer.extract_imports(source)

        assert "U" in imports
        assert imports["U"] == ("models", "User")

    def test_import_module(self):
        """Test import X."""
        source = """
import models
"""
        indexer = PythonIndexer()
        imports = indexer.extract_imports(source)

        assert "models" in imports
        assert imports["models"] == ("models", "models")

    def test_import_module_alias(self):
        """Test import X as Y."""
        source = """
import models as m
"""
        indexer = PythonIndexer()
        imports = indexer.extract_imports(source)

        assert "m" in imports
        assert imports["m"] == ("models", "models")

    def test_relative_import(self):
        """Test from . import X."""
        source = """
from . import sibling
from ..parent import User
"""
        indexer = PythonIndexer()
        imports = indexer.extract_imports(source)

        assert "sibling" in imports
        assert "User" in imports
        assert imports["sibling"][0].startswith(".")
        assert imports["User"][0].startswith("..")


class TestGetMemberId:
    """Tests for member ID extraction."""

    def test_python_method(self):
        """Python methods use name only."""
        assert get_member_id("validate", "python") == "validate"

    def test_java_method_with_params(self):
        """Java methods keep full signature."""
        assert get_member_id("process(Order,User)", "java") == "process(Order,User)"

    def test_java_field(self):
        """Java fields use name only."""
        assert get_member_id("count", "java") == "count"


class TestGetOverriddenMembers:
    """Tests for override detection."""

    def test_collects_direct_members(self):
        """Test that direct members are collected."""
        source = """
class Admin(User):
    role: str = "admin"

    def can_edit(self) -> bool:
        return True
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")

        admin_members = [c for c in constructs if c.qualname.startswith("Admin.")]
        overridden = get_overridden_members(admin_members, "Admin", "python")

        assert "role" in overridden
        assert "can_edit" in overridden


class TestInheritanceResolver:
    """Tests for inheritance chain resolution."""

    def test_same_file_inheritance(self):
        """Test resolving inheritance within same file."""
        source = """
class User:
    pass

class Admin(User):
    pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "models.py").write_text(source)

            indexer = PythonIndexer()
            constructs = indexer.index_file(source, "models.py")

            resolver = InheritanceResolver(
                repo_root=repo_path,
                language="python",
                indexer=indexer,
            )
            resolver.add_file("models.py", constructs, source)

            chain = resolver.get_inheritance_chain("models.py", "Admin")

            assert len(chain) == 1
            assert chain[0].path == "models.py"
            assert chain[0].qualname == "User"

    def test_grandparent_chain(self):
        """Test resolving full inheritance chain."""
        source = """
class User:
    pass

class Admin(User):
    pass

class SuperAdmin(Admin):
    pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "models.py").write_text(source)

            indexer = PythonIndexer()
            constructs = indexer.index_file(source, "models.py")

            resolver = InheritanceResolver(
                repo_root=repo_path,
                language="python",
                indexer=indexer,
            )
            resolver.add_file("models.py", constructs, source)

            chain = resolver.get_inheritance_chain("models.py", "SuperAdmin")

            assert len(chain) == 2
            qualnames = [e.qualname for e in chain]
            assert "Admin" in qualnames
            assert "User" in qualnames


class TestInheritanceDetection:
    """Integration tests for inheritance-aware change detection."""

    def test_parent_method_change_triggers_child(self, inheritance_repo: Path):
        """Changing parent method triggers child subscription."""
        repo = GitRepo(inheritance_repo)
        detector = Detector(repo)

        # Subscribe to Admin class
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        admin = indexer.find_construct(source, "models.py", "Admin", "class")
        assert admin is not None

        sub = Subscription(
            id="test-admin",
            path="models.py",
            start_line=admin.start_line,
            end_line=admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="Admin",
                interface_hash=admin.interface_hash,
                body_hash=admin.body_hash,
            ),
        )

        # Change User.validate() - parent of Admin
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name and self.email and len(self.name) > 1)"
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change validate")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should trigger because Admin inherits validate from User
        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "inherited_member_changed" in trigger.reasons
        assert trigger.details is not None
        assert "inherited_changes" in trigger.details
        assert trigger.details.get("source") == "inherited"

    def test_overridden_method_change_no_trigger(self, inheritance_repo: Path):
        """Changing parent method doesn't trigger if child overrides it."""
        repo = GitRepo(inheritance_repo)
        detector = Detector(repo)

        # First, add an override to Admin
        source = (inheritance_repo / "models.py").read_text()
        override_source = source.replace(
            "class Admin(User):",
            """class Admin(User):
    def validate(self) -> bool:
        \"\"\"Admin validation.\"\"\"
        return super().validate() and self.role == "admin"
"""
        ).replace(
            '"""Admin user."""\n\n    role',
            '"""Admin user."""\n    role'
        )

        # Actually, let me do a simpler replacement
        override_source = source.replace(
            '''class Admin(User):
    """Admin user."""

    role: str = "admin"''',
            '''class Admin(User):
    """Admin user."""

    role: str = "admin"

    def validate(self) -> bool:
        """Admin-specific validation."""
        return super().validate() and self.role == "admin"'''
        )

        write_file(inheritance_repo / "models.py", override_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Add override")

        # Now subscribe to Admin class
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        admin = indexer.find_construct(source, "models.py", "Admin", "class")
        assert admin is not None

        sub = Subscription(
            id="test-admin",
            path="models.py",
            start_line=admin.start_line,
            end_line=admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="Admin",
                interface_hash=admin.interface_hash,
                body_hash=admin.body_hash,
            ),
        )

        # Change User.validate()
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name and self.email and len(self.name) > 1)"
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change parent validate")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should NOT trigger for validate because Admin overrides it
        # But may trigger for other inherited changes
        if result.triggers:
            trigger = result.triggers[0]
            if trigger.details and "inherited_changes" in trigger.details:
                inherited = trigger.details["inherited_changes"]
                validate_changes = [c for c in inherited if c.get("member_name") == "validate"]
                assert len(validate_changes) == 0, "Overridden method should not trigger"

    def test_grandparent_change_triggers_grandchild(self, inheritance_repo: Path):
        """Changing grandparent method triggers grandchild subscription."""
        repo = GitRepo(inheritance_repo)
        detector = Detector(repo)

        # Subscribe to SuperAdmin class
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        super_admin = indexer.find_construct(source, "models.py", "SuperAdmin", "class")
        assert super_admin is not None

        sub = Subscription(
            id="test-super-admin",
            path="models.py",
            start_line=super_admin.start_line,
            end_line=super_admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="SuperAdmin",
                interface_hash=super_admin.interface_hash,
                body_hash=super_admin.body_hash,
            ),
        )

        # Change User.validate() - grandparent of SuperAdmin
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name)"
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change grandparent validate")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should trigger because SuperAdmin inherits validate through Admin from User
        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "inherited_member_changed" in trigger.reasons
        assert trigger.details is not None
        assert "inheritance_chain" in trigger.details
        # Chain should include both Admin and User
        chain = trigger.details["inheritance_chain"]
        chain_qualnames = [e["qualname"] for e in chain]
        assert "Admin" in chain_qualnames
        assert "User" in chain_qualnames


class TestIntermediateOverride:
    """Tests for intermediate override detection."""

    def test_intermediate_override_blocks_trigger(self, inheritance_repo: Path):
        """If Admin overrides User.validate, SuperAdmin shouldn't trigger on User.validate change."""
        repo = GitRepo(inheritance_repo)

        # Add override in Admin
        source = (inheritance_repo / "models.py").read_text()
        override_source = source.replace(
            '''class Admin(User):
    """Admin user."""

    role: str = "admin"''',
            '''class Admin(User):
    """Admin user."""

    role: str = "admin"

    def validate(self) -> bool:
        """Admin validation."""
        return True'''
        )

        write_file(inheritance_repo / "models.py", override_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Admin overrides validate")

        # Subscribe to SuperAdmin
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        super_admin = indexer.find_construct(source, "models.py", "SuperAdmin", "class")
        assert super_admin is not None

        sub = Subscription(
            id="test-super-admin",
            path="models.py",
            start_line=super_admin.start_line,
            end_line=super_admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="SuperAdmin",
                interface_hash=super_admin.interface_hash,
                body_hash=super_admin.body_hash,
            ),
        )

        detector = Detector(repo)

        # Change User.validate()
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return False"
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change User.validate")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # SuperAdmin inherits validate from Admin (which overrides), not User
        # So User.validate change should NOT trigger for SuperAdmin
        if result.triggers:
            trigger = result.triggers[0]
            if trigger.details and "inherited_changes" in trigger.details:
                inherited = trigger.details["inherited_changes"]
                # validate should not appear because Admin overrides it
                validate_in_user = [
                    c for c in inherited
                    if c.get("member_name") == "validate" and c.get("parent_qualname") == "User"
                ]
                assert len(validate_in_user) == 0, "User.validate shouldn't trigger - Admin overrides it"


class TestFieldInheritance:
    """Tests for inherited field change detection."""

    def test_parent_field_change_triggers_child(self, inheritance_repo: Path):
        """Changing a parent field triggers child subscription."""
        repo = GitRepo(inheritance_repo)
        detector = Detector(repo)

        # Subscribe to Admin class
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        admin = indexer.find_construct(source, "models.py", "Admin", "class")
        assert admin is not None

        sub = Subscription(
            id="test-admin",
            path="models.py",
            start_line=admin.start_line,
            end_line=admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="Admin",
                interface_hash=admin.interface_hash,
                body_hash=admin.body_hash,
            ),
        )

        # Change User.name field default value
        new_source = source.replace(
            'name: str = ""',
            'name: str = "Anonymous"'
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change User.name default")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Should trigger because Admin inherits name from User
        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        assert "inherited_member_changed" in trigger.reasons
        assert trigger.details is not None
        inherited = trigger.details.get("inherited_changes", [])
        name_changes = [c for c in inherited if c.get("member_name") == "name"]
        assert len(name_changes) == 1
        assert name_changes[0]["change_type"] == "CONTENT"


class TestMultipleInheritance:
    """Tests for Python multiple inheritance."""

    def test_multiple_base_classes_extracted(self):
        """Test that all base classes are extracted."""
        source = """
class Mixin:
    def helper(self):
        pass

class User:
    name: str = ""

class Admin(User, Mixin):
    role: str = "admin"
"""
        indexer = PythonIndexer()
        constructs = indexer.index_file(source, "test.py")
        admin = next(c for c in constructs if c.qualname == "Admin")

        assert admin.base_classes == ("User", "Mixin")

    def test_multiple_inheritance_triggers_from_first_parent(self):
        """Changes in first parent should trigger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize repo
            run_git(repo_path, "init")
            run_git(repo_path, "config", "user.email", "test@test.com")
            run_git(repo_path, "config", "user.name", "Test User")

            source = '''
class Mixin:
    def helper(self) -> str:
        return "help"

class User:
    name: str = ""

    def validate(self) -> bool:
        return bool(self.name)

class Admin(User, Mixin):
    role: str = "admin"
'''
            write_file(repo_path / "models.py", source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Initial")

            repo = GitRepo(repo_path)
            detector = Detector(repo)

            # Subscribe to Admin
            indexer = PythonIndexer()
            admin = indexer.find_construct(source, "models.py", "Admin", "class")
            assert admin is not None

            sub = Subscription(
                id="test-admin",
                path="models.py",
                start_line=admin.start_line,
                end_line=admin.end_line,
                semantic=SemanticTarget(
                    language="python",
                    kind="class",
                    qualname="Admin",
                    interface_hash=admin.interface_hash,
                    body_hash=admin.body_hash,
                ),
            )

            # Change User.validate (first parent)
            new_source = source.replace(
                "return bool(self.name)",
                "return len(self.name) > 0"
            )
            write_file(repo_path / "models.py", new_source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Change validate")

            base_ref = repo.resolve_ref("HEAD~1")
            target_ref = repo.resolve_ref("HEAD")

            result = detector.scan([sub], base_ref, target_ref)

            # Should trigger for User.validate
            assert len(result.triggers) == 1
            trigger = result.triggers[0]
            assert "inherited_member_changed" in trigger.reasons

    def test_multiple_inheritance_triggers_from_second_parent(self):
        """Changes in second parent (mixin) should also trigger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            run_git(repo_path, "init")
            run_git(repo_path, "config", "user.email", "test@test.com")
            run_git(repo_path, "config", "user.name", "Test User")

            source = '''
class Mixin:
    def helper(self) -> str:
        return "help"

class User:
    name: str = ""

class Admin(User, Mixin):
    role: str = "admin"
'''
            write_file(repo_path / "models.py", source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Initial")

            repo = GitRepo(repo_path)
            detector = Detector(repo)

            indexer = PythonIndexer()
            current_source = (repo_path / "models.py").read_text()
            admin = indexer.find_construct(current_source, "models.py", "Admin", "class")
            assert admin is not None

            sub = Subscription(
                id="test-admin",
                path="models.py",
                start_line=admin.start_line,
                end_line=admin.end_line,
                semantic=SemanticTarget(
                    language="python",
                    kind="class",
                    qualname="Admin",
                    interface_hash=admin.interface_hash,
                    body_hash=admin.body_hash,
                ),
            )

            # Change Mixin.helper (second parent)
            new_source = current_source.replace(
                'return "help"',
                'return "HELP"'
            )
            write_file(repo_path / "models.py", new_source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Change helper")

            base_ref = repo.resolve_ref("HEAD~1")
            target_ref = repo.resolve_ref("HEAD")

            result = detector.scan([sub], base_ref, target_ref)

            # Should trigger for Mixin.helper
            assert len(result.triggers) == 1
            trigger = result.triggers[0]
            assert "inherited_member_changed" in trigger.reasons
            inherited = trigger.details.get("inherited_changes", [])
            helper_changes = [c for c in inherited if c.get("member_name") == "helper"]
            assert len(helper_changes) == 1


class TestPropertyInheritance:
    """Tests for Python property inheritance."""

    def test_parent_property_change_triggers_child(self):
        """Changing a parent @property triggers child subscription."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            run_git(repo_path, "init")
            run_git(repo_path, "config", "user.email", "test@test.com")
            run_git(repo_path, "config", "user.name", "Test User")

            source = '''
class User:
    _name: str = ""

    @property
    def display_name(self) -> str:
        return self._name.title()

class Admin(User):
    role: str = "admin"
'''
            write_file(repo_path / "models.py", source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Initial")

            repo = GitRepo(repo_path)
            detector = Detector(repo)

            indexer = PythonIndexer()
            current_source = (repo_path / "models.py").read_text()
            admin = indexer.find_construct(current_source, "models.py", "Admin", "class")
            assert admin is not None

            sub = Subscription(
                id="test-admin",
                path="models.py",
                start_line=admin.start_line,
                end_line=admin.end_line,
                semantic=SemanticTarget(
                    language="python",
                    kind="class",
                    qualname="Admin",
                    interface_hash=admin.interface_hash,
                    body_hash=admin.body_hash,
                ),
            )

            # Change User.display_name property
            new_source = current_source.replace(
                "return self._name.title()",
                "return self._name.upper()"
            )
            write_file(repo_path / "models.py", new_source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Change property")

            base_ref = repo.resolve_ref("HEAD~1")
            target_ref = repo.resolve_ref("HEAD")

            result = detector.scan([sub], base_ref, target_ref)

            # Should trigger for display_name property
            assert len(result.triggers) == 1
            trigger = result.triggers[0]
            assert "inherited_member_changed" in trigger.reasons


class TestJavaInheritance:
    """Tests for Java inheritance detection."""

    def test_java_base_class_extraction(self):
        """Test Java extends extraction."""
        try:
            from codesub.semantic import JavaIndexer
        except ImportError:
            pytest.skip("tree-sitter-java not installed")

        source = """
public class Admin extends User {
    private String role = "admin";
}
"""
        indexer = JavaIndexer()
        constructs = indexer.index_file(source, "Admin.java")
        admin = next((c for c in constructs if c.qualname == "Admin"), None)
        assert admin is not None
        assert admin.base_classes == ("User",)

    def test_java_implements_extraction(self):
        """Test Java implements extraction."""
        try:
            from codesub.semantic import JavaIndexer
        except ImportError:
            pytest.skip("tree-sitter-java not installed")

        source = """
public class UserService implements Service, Validator {
    public void serve() {}
}
"""
        indexer = JavaIndexer()
        constructs = indexer.index_file(source, "UserService.java")
        service = next((c for c in constructs if c.qualname == "UserService"), None)
        assert service is not None
        assert "Service" in service.base_classes
        assert "Validator" in service.base_classes

    def test_java_extends_and_implements(self):
        """Test Java with both extends and implements."""
        try:
            from codesub.semantic import JavaIndexer
        except ImportError:
            pytest.skip("tree-sitter-java not installed")

        source = """
public class AdminService extends BaseService implements Validator {
    public void validate() {}
}
"""
        indexer = JavaIndexer()
        constructs = indexer.index_file(source, "AdminService.java")
        admin_service = next((c for c in constructs if c.qualname == "AdminService"), None)
        assert admin_service is not None
        assert admin_service.base_classes is not None
        assert "BaseService" in admin_service.base_classes
        assert "Validator" in admin_service.base_classes

    def test_java_import_extraction(self):
        """Test Java import extraction."""
        try:
            from codesub.semantic import JavaIndexer
        except ImportError:
            pytest.skip("tree-sitter-java not installed")

        source = """
import com.example.models.User;
import com.example.services.UserService;

public class AdminController {
}
"""
        indexer = JavaIndexer()
        imports = indexer.extract_imports(source)

        assert "User" in imports
        assert imports["User"] == ("com.example.models.User", "User")
        assert "UserService" in imports


class TestContainerInheritance:
    """Tests for container subscriptions with inheritance."""

    def test_container_subscription_with_inheritance(self, inheritance_repo: Path):
        """Container subscription should also detect inherited member changes."""
        repo = GitRepo(inheritance_repo)
        detector = Detector(repo)

        # Subscribe to Admin class with include_members=True
        indexer = PythonIndexer()
        source = (inheritance_repo / "models.py").read_text()
        admin = indexer.find_construct(source, "models.py", "Admin", "class")
        assert admin is not None

        # Get admin's members for baseline
        admin_members = indexer.get_container_members(source, "models.py", "Admin")
        baseline_members = {
            m.qualname.split(".")[-1]: MemberFingerprint(
                kind=m.kind,
                interface_hash=m.interface_hash,
                body_hash=m.body_hash,
            )
            for m in admin_members
        }

        sub = Subscription(
            id="test-admin-container",
            path="models.py",
            start_line=admin.start_line,
            end_line=admin.end_line,
            semantic=SemanticTarget(
                language="python",
                kind="class",
                qualname="Admin",
                interface_hash=admin.interface_hash,
                body_hash=admin.body_hash,
                include_members=True,
                baseline_members=baseline_members,
                baseline_container_qualname="Admin",
            ),
        )

        # Change User.validate() - inherited method
        new_source = source.replace(
            "return bool(self.name and self.email)",
            "return bool(self.name)"
        )
        write_file(inheritance_repo / "models.py", new_source)
        run_git(inheritance_repo, "add", ".")
        run_git(inheritance_repo, "commit", "-m", "Change inherited method")

        base_ref = repo.resolve_ref("HEAD~1")
        target_ref = repo.resolve_ref("HEAD")

        result = detector.scan([sub], base_ref, target_ref)

        # Container subscription should also trigger for inherited changes
        assert len(result.triggers) == 1
        trigger = result.triggers[0]
        # Should have inherited_member_changed in reasons
        assert "inherited_member_changed" in trigger.reasons


class TestExternalBaseClass:
    """Tests for external (unresolvable) base classes."""

    def test_external_base_class_no_trigger(self):
        """External base classes should be silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            run_git(repo_path, "init")
            run_git(repo_path, "config", "user.email", "test@test.com")
            run_git(repo_path, "config", "user.name", "Test User")

            # ABC is external (from stdlib), cannot be resolved
            source = '''
from abc import ABC

class BaseService(ABC):
    def process(self):
        pass

class UserService(BaseService):
    def handle(self):
        pass
'''
            write_file(repo_path / "service.py", source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Initial")

            repo = GitRepo(repo_path)
            detector = Detector(repo)

            indexer = PythonIndexer()
            current_source = (repo_path / "service.py").read_text()
            user_service = indexer.find_construct(current_source, "service.py", "UserService", "class")
            assert user_service is not None

            sub = Subscription(
                id="test-user-service",
                path="service.py",
                start_line=user_service.start_line,
                end_line=user_service.end_line,
                semantic=SemanticTarget(
                    language="python",
                    kind="class",
                    qualname="UserService",
                    interface_hash=user_service.interface_hash,
                    body_hash=user_service.body_hash,
                ),
            )

            # Change BaseService.process
            new_source = current_source.replace(
                "def process(self):",
                "def process(self, data):"
            )
            write_file(repo_path / "service.py", new_source)
            run_git(repo_path, "add", ".")
            run_git(repo_path, "commit", "-m", "Change base method")

            base_ref = repo.resolve_ref("HEAD~1")
            target_ref = repo.resolve_ref("HEAD")

            result = detector.scan([sub], base_ref, target_ref)

            # Should trigger for BaseService.process (in-repo base class)
            # ABC is external and will be skipped
            assert len(result.triggers) == 1
            trigger = result.triggers[0]
            assert "inherited_member_changed" in trigger.reasons
            # The change should be from BaseService, not ABC
            inherited = trigger.details.get("inherited_changes", [])
            assert any(c.get("parent_qualname") == "BaseService" for c in inherited)
