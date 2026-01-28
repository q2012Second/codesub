"""Domain models for the order management system."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


class OrderStatus(Enum):
    """Order lifecycle states."""
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


@dataclass
class User:
    """Customer account."""
    id: str
    email: str
    name: str
    region: str = "US-CA"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Product:
    """Catalog item."""
    id: str
    name: str
    price: Decimal
    stock: int = 0

    def is_available(self, quantity: int = 1) -> bool:
        return self.stock >= quantity


@dataclass
class OrderItem:
    """Line item in an order."""
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass
class Order:
    """Customer order."""
    id: str
    user_id: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    shipping_address: Optional[str] = None
    stripe_payment_id: Optional[str] = None
    shipfast_tracking_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def subtotal(self) -> Decimal:
        return sum(item.subtotal for item in self.items)
