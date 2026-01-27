"""Advanced Python types for semantic subscription testing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import (
    Any,
    Dict,
    Generic,
    List,
    NamedTuple,
    Optional,
    Protocol,
    TypedDict,
    TypeVar,
)

# =============================================================================
# Module-Level Variables
# =============================================================================

# Simple constants
MAX_ITEMS = 100
DEFAULT_TIMEOUT = 30

# Typed constants
API_VERSION: str = "v2.0"
RETRY_COUNT: int = 3
DEBUG_ENABLED: bool = False

# Complex typed constants
DEFAULT_HEADERS: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

ALLOWED_METHODS: list[str] = ["GET", "POST", "PUT", "DELETE"]

# Annotation without value
pending_tasks: list[str]


# =============================================================================
# Enums
# =============================================================================


class Status(Enum):
    """Status enumeration."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        return self in (Status.COMPLETED, Status.CANCELLED)


class Priority(IntEnum):
    """Priority levels."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class Color(Enum):
    RED = auto()
    GREEN = auto()
    BLUE = auto()


# =============================================================================
# TypedDicts
# =============================================================================


class UserDict(TypedDict):
    """User as TypedDict."""

    id: int
    username: str
    email: str


class UserDictPartial(TypedDict, total=False):
    """User with optional fields."""

    id: int
    username: str
    nickname: str
    avatar_url: str


class AddressDict(TypedDict):
    """Address TypedDict."""

    street: str
    city: str
    country: str
    postal_code: str


class CustomerDict(TypedDict):
    """Nested TypedDict."""

    user: UserDict
    address: AddressDict
    premium: bool


# =============================================================================
# NamedTuples
# =============================================================================


class Point(NamedTuple):
    """2D point as NamedTuple."""

    x: float
    y: float

    def distance_from_origin(self) -> float:
        return (self.x**2 + self.y**2) ** 0.5


class Rectangle(NamedTuple):
    """Rectangle defined by two corners."""

    top_left: Point
    bottom_right: Point
    color: str = "black"

    @property
    def width(self) -> float:
        return abs(self.bottom_right.x - self.top_left.x)

    @property
    def height(self) -> float:
        return abs(self.bottom_right.y - self.top_left.y)


# =============================================================================
# Protocols
# =============================================================================


class Drawable(Protocol):
    """Protocol for drawable objects."""

    def draw(self) -> None: ...

    def get_bounds(self) -> tuple[float, float, float, float]: ...


class Serializable(Protocol):
    """Protocol for serializable objects."""

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Serializable": ...


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class SimpleData:
    """Simple dataclass."""

    name: str
    value: int
    active: bool = True


@dataclass
class ComplexData:
    """Dataclass with complex fields."""

    id: int
    name: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None

    def add_tag(self, tag: str) -> None:
        self.tags.append(tag)

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags


@dataclass(frozen=True)
class ImmutableConfig:
    """Frozen dataclass."""

    host: str
    port: int
    ssl: bool = True
    timeout: int = 30


# =============================================================================
# Abstract Base Classes
# =============================================================================


class BaseHandler(ABC):
    """Abstract base handler."""

    name: str = "base"
    version: int = 1

    @abstractmethod
    def handle(self, data: Any) -> Any:
        """Handle the data."""
        pass

    @abstractmethod
    def validate(self, data: Any) -> bool:
        """Validate the data."""
        pass

    def log(self, message: str) -> None:
        """Log a message."""
        print(f"[{self.name}] {message}")


# =============================================================================
# Generic Classes
# =============================================================================

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


class Container(Generic[T]):
    """Generic container class."""

    default_capacity: int = 10

    def __init__(self, items: list[T] | None = None) -> None:
        self._items: list[T] = items or []

    def add(self, item: T) -> None:
        self._items.append(item)

    def get(self, index: int) -> T | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    @property
    def count(self) -> int:
        return len(self._items)


class Cache(Generic[K, V]):
    """Generic cache with key-value types."""

    max_size: int = 1000
    ttl_seconds: int = 3600

    def __init__(self) -> None:
        self._store: dict[K, V] = {}

    def set(self, key: K, value: V) -> None:
        self._store[key] = value

    def get(self, key: K, default: V | None = None) -> V | None:
        return self._store.get(key, default)


# =============================================================================
# Regular Classes with Various Members
# =============================================================================


class ServiceConfig:
    """Configuration class with various member types."""

    # Class variables
    instance_count: int = 0
    default_timeout: int = 30
    _registry: dict[str, "ServiceConfig"] = {}

    def __init__(self, name: str, endpoint: str) -> None:
        self.name = name
        self.endpoint = endpoint
        ServiceConfig.instance_count += 1

    @classmethod
    def get_instance_count(cls) -> int:
        """Get total instance count."""
        return cls.instance_count

    @classmethod
    def register(cls, config: "ServiceConfig") -> None:
        """Register a config instance."""
        cls._registry[config.name] = config

    @staticmethod
    def validate_endpoint(endpoint: str) -> bool:
        """Validate endpoint URL."""
        return endpoint.startswith(("http://", "https://"))

    @property
    def full_url(self) -> str:
        """Get full URL."""
        return f"{self.endpoint}/api"

    @property
    def is_secure(self) -> bool:
        """Check if using HTTPS."""
        return self.endpoint.startswith("https://")


class Calculator:
    """Calculator with decorated methods."""

    precision: int = 2

    @staticmethod
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    @staticmethod
    def subtract(a: float, b: float) -> float:
        """Subtract b from a."""
        return a - b

    @classmethod
    def set_precision(cls, precision: int) -> None:
        """Set decimal precision."""
        cls.precision = precision

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        return round(a * b, self.precision)

    def divide(self, a: float, b: float) -> float:
        """Divide a by b."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return round(a / b, self.precision)
