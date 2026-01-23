"""Data models for the application."""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class User:
    """Represents a user in the system."""
    id: int
    username: str
    email: str
    created_at: datetime
    is_active: bool = True

    def full_name(self) -> str:
        return self.username


@dataclass
class Product:
    """Represents a product in the catalog."""
    id: int
    name: str
    price: float
    description: Optional[str] = None
    stock: int = 0

    def is_available(self) -> bool:
        return self.stock > 0

    def apply_discount(self, percent: float) -> float:
        """Apply discount and return new price."""
        return self.price * (1 - percent / 100)


@dataclass
class Order:
    """Represents a customer order."""
    id: int
    user_id: int
    items: List[int]
    total: float
    status: str = "pending"
    created_at: Optional[datetime] = None

    def is_completed(self) -> bool:
        return self.status == "completed"

    def cancel(self) -> None:
        self.status = "cancelled"
