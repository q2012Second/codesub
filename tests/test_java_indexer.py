"""Tests for JavaIndexer."""

import pytest

from codesub.semantic.java_indexer import JavaIndexer


@pytest.fixture
def indexer():
    """Create a JavaIndexer instance."""
    return JavaIndexer()


class TestClassDeclarations:
    """Tests for class declaration extraction."""

    def test_simple_class(self, indexer):
        """Test extraction of a simple class."""
        source = """
public class User {
    private String name;
}
"""
        constructs = indexer.index_file(source, "User.java")

        # Find the class
        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 1
        assert class_constructs[0].qualname == "User"

    def test_class_with_extends(self, indexer):
        """Test class that extends another class."""
        source = """
public class Admin extends User {
}
"""
        constructs = indexer.index_file(source, "Admin.java")

        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 1
        assert class_constructs[0].qualname == "Admin"

    def test_class_with_implements(self, indexer):
        """Test class that implements interfaces."""
        source = """
public class UserService implements Service, Serializable {
}
"""
        constructs = indexer.index_file(source, "UserService.java")

        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 1
        assert class_constructs[0].qualname == "UserService"

    def test_nested_class(self, indexer):
        """Test nested class extraction."""
        source = """
public class Outer {
    public class Inner {
        private int value;
    }
}
"""
        constructs = indexer.index_file(source, "Outer.java")

        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 2
        qualnames = {c.qualname for c in class_constructs}
        assert qualnames == {"Outer", "Outer.Inner"}

    def test_annotated_class(self, indexer):
        """Test class with annotations."""
        source = """
@Entity
@Table(name = "users")
public class User {
}
"""
        constructs = indexer.index_file(source, "User.java")

        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 1
        assert class_constructs[0].qualname == "User"


class TestInterfaceDeclarations:
    """Tests for interface declaration extraction."""

    def test_simple_interface(self, indexer):
        """Test extraction of a simple interface."""
        source = """
public interface Service {
    void execute();
}
"""
        constructs = indexer.index_file(source, "Service.java")

        interface_constructs = [c for c in constructs if c.kind == "interface"]
        assert len(interface_constructs) == 1
        assert interface_constructs[0].qualname == "Service"

    def test_interface_extends(self, indexer):
        """Test interface that extends another interface."""
        source = """
public interface ExtendedService extends Service, Runnable {
}
"""
        constructs = indexer.index_file(source, "ExtendedService.java")

        interface_constructs = [c for c in constructs if c.kind == "interface"]
        assert len(interface_constructs) == 1
        assert interface_constructs[0].qualname == "ExtendedService"


class TestEnumDeclarations:
    """Tests for enum declaration extraction."""

    def test_simple_enum(self, indexer):
        """Test extraction of a simple enum."""
        source = """
public enum Status {
    PENDING,
    ACTIVE,
    COMPLETED
}
"""
        constructs = indexer.index_file(source, "Status.java")

        enum_constructs = [c for c in constructs if c.kind == "enum"]
        assert len(enum_constructs) == 1
        assert enum_constructs[0].qualname == "Status"

    def test_enum_constants(self, indexer):
        """Test enum constant extraction."""
        source = """
public enum Status {
    PENDING,
    ACTIVE,
    COMPLETED
}
"""
        constructs = indexer.index_file(source, "Status.java")

        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 3
        qualnames = {c.qualname for c in field_constructs}
        assert qualnames == {"Status.PENDING", "Status.ACTIVE", "Status.COMPLETED"}

        # All enum constants should have role="const"
        for c in field_constructs:
            assert c.role == "const"

    def test_enum_with_arguments(self, indexer):
        """Test enum constants with constructor arguments."""
        source = """
public enum Status {
    PENDING("Waiting"),
    ACTIVE("In Progress"),
    COMPLETED("Done");

    private String description;

    Status(String description) {
        this.description = description;
    }
}
"""
        constructs = indexer.index_file(source, "Status.java")

        # Check enum constants
        const_constructs = [c for c in constructs if c.role == "const"]
        assert len(const_constructs) == 3

        # Different arguments should produce different body hashes
        body_hashes = {c.body_hash for c in const_constructs}
        assert len(body_hashes) == 3


class TestFieldDeclarations:
    """Tests for field declaration extraction."""

    def test_simple_field(self, indexer):
        """Test extraction of a simple field."""
        source = """
public class User {
    private String name;
}
"""
        constructs = indexer.index_file(source, "User.java")

        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 1
        assert field_constructs[0].qualname == "User.name"
        assert field_constructs[0].role is None

    def test_static_final_constant(self, indexer):
        """Test extraction of a static final constant."""
        source = """
public class Config {
    public static final int MAX_RETRIES = 3;
}
"""
        constructs = indexer.index_file(source, "Config.java")

        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 1
        assert field_constructs[0].qualname == "Config.MAX_RETRIES"
        assert field_constructs[0].role == "const"

    def test_multi_declarator_field(self, indexer):
        """Test extraction of fields with multiple declarators."""
        source = """
public class Point {
    private int x, y;
}
"""
        constructs = indexer.index_file(source, "Point.java")

        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 2
        qualnames = {c.qualname for c in field_constructs}
        assert qualnames == {"Point.x", "Point.y"}

    def test_field_with_initializer(self, indexer):
        """Test field with initializer value."""
        source = """
public class Counter {
    private int count = 0;
}
"""
        constructs = indexer.index_file(source, "Counter.java")

        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 1

        # Changing the initializer should change the body hash
        source2 = """
public class Counter {
    private int count = 100;
}
"""
        constructs2 = indexer.index_file(source2, "Counter.java")
        field_constructs2 = [c for c in constructs2 if c.kind == "field"]

        assert field_constructs[0].body_hash != field_constructs2[0].body_hash


class TestMethodDeclarations:
    """Tests for method declaration extraction."""

    def test_simple_method(self, indexer):
        """Test extraction of a simple method."""
        source = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
"""
        constructs = indexer.index_file(source, "Calculator.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 1
        assert method_constructs[0].qualname == "Calculator.add(int,int)"

    def test_overloaded_methods(self, indexer):
        """Test extraction of overloaded methods."""
        source = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }

    public double add(double a, double b) {
        return a + b;
    }

    public int add(int a, int b, int c) {
        return a + b + c;
    }
}
"""
        constructs = indexer.index_file(source, "Calculator.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 3

        qualnames = {c.qualname for c in method_constructs}
        assert qualnames == {
            "Calculator.add(int,int)",
            "Calculator.add(double,double)",
            "Calculator.add(int,int,int)",
        }

    def test_method_with_varargs(self, indexer):
        """Test extraction of method with varargs."""
        source = """
public class Utils {
    public String concat(String... parts) {
        return String.join("", parts);
    }
}
"""
        constructs = indexer.index_file(source, "Utils.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 1
        # Varargs should show as String...
        assert "String..." in method_constructs[0].qualname

    def test_method_with_generics(self, indexer):
        """Test extraction of method with generic types."""
        source = """
public class Container {
    public <T> T getValue(Class<T> type) {
        return null;
    }
}
"""
        constructs = indexer.index_file(source, "Container.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 1

    def test_constructor(self, indexer):
        """Test extraction of constructors."""
        source = """
public class User {
    private String name;

    public User() {
        this.name = "";
    }

    public User(String name) {
        this.name = name;
    }
}
"""
        constructs = indexer.index_file(source, "User.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 2

        qualnames = {c.qualname for c in method_constructs}
        assert qualnames == {"User.User()", "User.User(String)"}

    def test_method_body_hash_changes(self, indexer):
        """Test that method body changes are detected."""
        source1 = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
"""
        source2 = """
public class Calculator {
    public int add(int a, int b) {
        return a + b + 1;  // Changed implementation
    }
}
"""
        constructs1 = indexer.index_file(source1, "Calculator.java")
        constructs2 = indexer.index_file(source2, "Calculator.java")

        method1 = [c for c in constructs1 if c.kind == "method"][0]
        method2 = [c for c in constructs2 if c.kind == "method"][0]

        # Same interface (signature)
        assert method1.interface_hash == method2.interface_hash
        # Different body
        assert method1.body_hash != method2.body_hash


class TestFindConstruct:
    """Tests for find_construct method."""

    def test_find_class(self, indexer):
        """Test finding a class by qualname."""
        source = """
public class User {
    private String name;
}
"""
        construct = indexer.find_construct(source, "User.java", "User")
        assert construct is not None
        assert construct.kind == "class"
        assert construct.qualname == "User"

    def test_find_method(self, indexer):
        """Test finding a method by qualname."""
        source = """
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
"""
        construct = indexer.find_construct(
            source, "Calculator.java", "Calculator.add(int,int)"
        )
        assert construct is not None
        assert construct.kind == "method"

    def test_find_with_kind_filter(self, indexer):
        """Test finding construct with kind filter."""
        source = """
public class User {
    private String name;
    public String name() {
        return this.name;
    }
}
"""
        # Without kind filter, this might be ambiguous
        # With kind filter, we can be specific
        field = indexer.find_construct(source, "User.java", "User.name", kind="field")
        assert field is not None
        assert field.kind == "field"

        # Method has different qualname due to params
        method = indexer.find_construct(
            source, "User.java", "User.name()", kind="method"
        )
        assert method is not None
        assert method.kind == "method"

    def test_find_not_found(self, indexer):
        """Test that find_construct returns None for non-existent construct."""
        source = """
public class User {
    private String name;
}
"""
        construct = indexer.find_construct(source, "User.java", "User.nonexistent")
        assert construct is None


class TestNestedScopes:
    """Tests for nested class and method scopes."""

    def test_deeply_nested_classes(self, indexer):
        """Test deeply nested class extraction."""
        source = """
public class Outer {
    public class Middle {
        public class Inner {
            private int value;
        }
    }
}
"""
        constructs = indexer.index_file(source, "Outer.java")

        class_constructs = [c for c in constructs if c.kind == "class"]
        assert len(class_constructs) == 3

        qualnames = {c.qualname for c in class_constructs}
        assert qualnames == {"Outer", "Outer.Middle", "Outer.Middle.Inner"}

        # Check nested field
        field_constructs = [c for c in constructs if c.kind == "field"]
        assert len(field_constructs) == 1
        assert field_constructs[0].qualname == "Outer.Middle.Inner.value"

    def test_method_in_nested_class(self, indexer):
        """Test method extraction in nested class."""
        source = """
public class Outer {
    public class Inner {
        public void doSomething() {
        }
    }
}
"""
        constructs = indexer.index_file(source, "Outer.java")

        method_constructs = [c for c in constructs if c.kind == "method"]
        assert len(method_constructs) == 1
        assert method_constructs[0].qualname == "Outer.Inner.doSomething()"


class TestParseErrors:
    """Tests for handling parse errors."""

    def test_parse_error_flag(self, indexer):
        """Test that parse errors are flagged on constructs."""
        source = """
public class User {
    private String name
    // Missing semicolon above
}
"""
        constructs = indexer.index_file(source, "User.java")

        # Even with parse errors, some constructs may be extracted
        # All should have has_parse_error=True
        for c in constructs:
            assert c.has_parse_error is True
